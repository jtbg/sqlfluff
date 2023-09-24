"""Individual segment parsers.

Matchable objects which return individual segments.
"""

from abc import abstractmethod
from typing import Any, Collection, Dict, Optional, Sequence, Tuple, Type, Union
from uuid import uuid4

import regex

from sqlfluff.core.parser.context import ParseContext
from sqlfluff.core.parser.match_result import MatchResult2
from sqlfluff.core.parser.matchable import Matchable
from sqlfluff.core.parser.segments import BaseSegment, RawSegment
from sqlfluff.core.parser.types import SimpleHintType


class BaseParser(Matchable):
    """An abstract class from which other Parsers should inherit."""

    # Meta segments are handled separately. All Parser elements
    # are assumed to be not meta.
    is_meta: bool = False

    @abstractmethod
    def __init__(
        self,
        raw_class: Type[RawSegment],
        type: Optional[Union[str, Tuple[str, ...]]] = None,
        optional: bool = False,
        # The following kwargs are passed on to the segment:
        trim_chars: Optional[Tuple[str, ...]] = None,
    ) -> None:
        self.raw_class = raw_class
        self.type: Union[str, Tuple[str, ...]] = type or raw_class.type
        self.optional = optional
        self._trim_chars = trim_chars
        # Generate a cache key
        self._cache_key = uuid4().hex

    def cache_key(self) -> str:
        """Get the cache key for this parser.

        For parsers, they're unique per-instance.
        """
        return self._cache_key

    def is_optional(self) -> bool:
        """Return whether this element is optional."""
        return self.optional

    def _match2_at(self, idx: int, types: Sequence[str]) -> MatchResult2:
        """Construct a MatchResult2 at a given index.

        This is a helper function for reuse by other parsers.
        """
        segment_kwargs: Dict[str, Any] = {}
        _types: Tuple[str, ...] = ()
        if isinstance(self.type, str):
            _types += (self.type,)
        elif isinstance(self.type, tuple):
            _types += self.type
        if types:
            # Prepend, not append, so self.type is still in first position.
            _types = _types + tuple(types)
        if _types:
            # TODO: We're using a private attribute here, which feels a bit wrong.
            _new_types = set(_types).difference(self.raw_class._class_types)
            segment_kwargs["type"] = tuple(_new_types)
        if self._trim_chars:
            segment_kwargs["trim_chars"] = self._trim_chars
        return MatchResult2(
            matched_slice=slice(idx, idx + 1),
            matched_class=self.raw_class,
            segment_kwargs=segment_kwargs,
        )


class TypedParser(BaseParser):
    """An object which matches and returns raw segments based on types."""

    def __init__(
        self,
        template: str,
        raw_class: Type[RawSegment],
        type: Optional[Union[str, Tuple[str, ...]]] = None,
        optional: bool = False,
        trim_chars: Optional[Tuple[str, ...]] = None,
    ) -> None:
        # NB: the template in this case is the _target_ type.
        # The type kwarg is the eventual type.
        self.template = template
        # Pre-calculate the appropriate frozenset for matching later.
        _target_types: Tuple[str, ...] = (template,)
        if type is not None and type != template:
            _types: Tuple[str, ...]
            if isinstance(type, str):
                _types = (type,)
            else:
                _types = type
            # NOTE: we PREPEND the specified types, not APPEND.
            # This is so the *specified* type becomes the top level
            # type, not the template.
            _target_types = _types + _target_types
        self._target_types = frozenset(_target_types)
        super().__init__(
            raw_class=raw_class,
            # NOTE: We pass the type as a tuple. After matching it is important
            # that the original type is still preserved as one of the new types.
            # The new `type` becomes the "main" type, but the template will still
            # be part of the resulting `class_types`.
            type=_target_types,
            optional=optional,
            trim_chars=trim_chars,
        )

    def __repr__(self) -> str:
        return f"<TypedParser: {self.template!r}>"

    def simple(
        self, parse_context: ParseContext, crumbs: Optional[Tuple[str, ...]] = None
    ) -> SimpleHintType:
        """Does this matcher support a uppercase hash matching route?

        TypedParser segment doesn't support matching against raw strings,
        but it does support it against types. We'll match against the
        both the template _and_ the resulting type too, so that we
        also support re-matching.
        """
        return frozenset(), self._target_types

    def match2(
        self,
        segments: Sequence["BaseSegment"],
        idx: int,
        parse_context: "ParseContext",
    ) -> MatchResult2:
        """Match against this matcher."""
        if segments[idx].is_type(self.template):
            return self._match2_at(idx, segments[idx].class_types)
        return MatchResult2.empty_at(idx)


class StringParser(BaseParser):
    """An object which matches and returns raw segments based on strings."""

    def __init__(
        self,
        template: str,
        raw_class: Type[RawSegment],
        type: Optional[Union[str, Tuple[str, ...]]] = None,
        optional: bool = False,
        trim_chars: Optional[Tuple[str, ...]] = None,
    ):
        self.template = template.upper()
        # Create list version upfront to avoid recreating it multiple times.
        self._simple = frozenset((self.template,))
        super().__init__(
            raw_class=raw_class,
            type=type,
            optional=optional,
            trim_chars=trim_chars,
        )

    def __repr__(self) -> str:
        return f"<StringParser: {self.template!r}>"

    def simple(
        self, parse_context: "ParseContext", crumbs: Optional[Tuple[str, ...]] = None
    ) -> SimpleHintType:
        """Return simple options for this matcher.

        Because string matchers are not case sensitive we can
        just return the template here.
        """
        return self._simple, frozenset()

    def match2(
        self,
        segments: Sequence["BaseSegment"],
        idx: int,
        parse_context: "ParseContext",
    ) -> MatchResult2:
        """Match against this matcher.

        NOTE: We check that the segment is also code to avoid matching
        unexpected comments.
        """
        if segments[idx].raw_upper == self.template and segments[idx].is_code:
            return self._match2_at(idx, segments[idx].class_types)
        return MatchResult2.empty_at(idx)


class MultiStringParser(BaseParser):
    """An object which matches and returns raw segments on a collection of strings."""

    def __init__(
        self,
        templates: Collection[str],
        raw_class: Type[RawSegment],
        type: Optional[Union[str, Tuple[str, ...]]] = None,
        optional: bool = False,
        trim_chars: Optional[Tuple[str, ...]] = None,
    ):
        self.templates = {template.upper() for template in templates}
        # Create list version upfront to avoid recreating it multiple times.
        self._simple = frozenset(self.templates)
        super().__init__(
            raw_class=raw_class,
            type=type,
            optional=optional,
            trim_chars=trim_chars,
        )

    def __repr__(self) -> str:
        return f"<MultiStringParser: {self.templates!r}>"

    def simple(
        self, parse_context: "ParseContext", crumbs: Optional[Tuple[str, ...]] = None
    ) -> SimpleHintType:
        """Return simple options for this matcher.

        Because string matchers are not case sensitive we can
        just return the templates here.
        """
        return self._simple, frozenset()

    def match2(
        self,
        segments: Sequence["BaseSegment"],
        idx: int,
        parse_context: "ParseContext",
    ) -> MatchResult2:
        """Match against this matcher.

        NOTE: We check that the segment is also code to avoid matching
        unexpected comments.
        """
        if segments[idx].is_code and segments[idx].raw_upper in self.templates:
            return self._match2_at(idx, segments[idx].class_types)
        return MatchResult2.empty_at(idx)


class RegexParser(BaseParser):
    """An object which matches and returns raw segments based on a regex."""

    def __init__(
        self,
        template: str,
        raw_class: Type[RawSegment],
        type: Optional[Union[str, Tuple[str, ...]]] = None,
        optional: bool = False,
        anti_template: Optional[str] = None,
        trim_chars: Optional[Tuple[str, ...]] = None,
    ):
        # Store the optional anti-template
        self.template = template
        self.anti_template = anti_template
        # Compile regexes upfront to avoid repeated overhead
        self._anti_template = regex.compile(anti_template or r"", regex.IGNORECASE)
        self._template = regex.compile(template, regex.IGNORECASE)
        super().__init__(
            raw_class=raw_class,
            type=type,
            optional=optional,
            trim_chars=trim_chars,
        )

    def __repr__(self) -> str:
        return f"<RegexParser: {self.template!r}>"

    def simple(
        cls, parse_context: ParseContext, crumbs: Optional[Tuple[str, ...]] = None
    ) -> None:
        """Does this matcher support a uppercase hash matching route?

        Regex segment does NOT for now. We might need to later for efficiency.
        """
        return None

    def match2(
        self,
        segments: Sequence["BaseSegment"],
        idx: int,
        parse_context: "ParseContext",
    ) -> MatchResult2:
        """Match against this matcher.

        NOTE: This method uses .raw_upper and so case sensitivity is
        not supported.
        """
        _raw = segments[idx].raw_upper
        result = self._template.match(_raw)
        if result:
            result_string = result.group(0)
            # Check that we've fully matched
            if result_string == _raw:
                # Check that the anti_template (if set) hasn't also matched
                if not self.anti_template or not self._anti_template.match(_raw):
                    return self._match2_at(idx, segments[idx].class_types)
        return MatchResult2.empty_at(idx)

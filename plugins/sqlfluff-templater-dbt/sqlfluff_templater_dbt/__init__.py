"""Defines the hook endpoints for the dbt templater plugin."""

from sqlfluff.core.osmosis import DbtProjectContainer
from sqlfluff_templater_dbt.templater import DbtTemplater
from sqlfluff.core.plugin import hookimpl


dbt_project_container = DbtProjectContainer()


@hookimpl
def get_templaters():
    """Get templaters."""

    def create_templater(**kwargs):
        return DbtTemplater(dbt_project_container=dbt_project_container, **kwargs)

    create_templater.name = DbtTemplater.name
    return [create_templater]

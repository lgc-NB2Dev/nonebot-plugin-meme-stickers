from collections.abc import Awaitable
from typing import TYPE_CHECKING, Any, Generic, Protocol, TypeVar

from cookit import TypeDecoCollector
from httpx import AsyncClient
from yarl import URL

from .config import config
from .models import (
    FileSource,
    FileSourceGitHub,
    FileSourceGitHubBranch,
    FileSourceGitHubTag,
    FileSourceURL,
)
from .utils import request_retry

if TYPE_CHECKING:
    from httpx import Response

M = TypeVar("M", bound=FileSource)
M_contra = TypeVar("M_contra", bound=FileSource, contravariant=True)


class SourceFetcher(Protocol, Generic[M_contra]):
    def __call__(self, source: M_contra, *paths: str) -> Awaitable["Response"]: ...


source_fetcher = TypeDecoCollector[FileSource, SourceFetcher[Any]]()


@source_fetcher(FileSourceURL)
async def fetch_url_source(source: FileSourceURL, *paths: str) -> "Response":
    url = str(URL(source.url).joinpath(*paths))

    async def fetch(cli: AsyncClient) -> "Response":
        return (await cli.get(url)).raise_for_status()

    async with AsyncClient(proxy=config.proxy, follow_redirects=True) as cli:
        return await request_retry()(fetch)(cli)


def format_github_url(source: FileSourceGitHub):
    v = {
        "owner": source.owner,
        "repo": source.repo,
        "ref": (
            source.branch if isinstance(source, FileSourceGitHubBranch) else source.tag
        ),
        "ref_path": (
            f"refs/heads/{source.branch}"
            if isinstance(source, FileSourceGitHubBranch)
            else f"refs/tags/{source.tag}"
        ),
        "path": source.path,
    }
    return config.meme_stickers_github_url_template.format_map(v)


@source_fetcher(FileSourceGitHubTag)
@source_fetcher(FileSourceGitHubBranch)
async def fetch_github_source(
    source: FileSourceGitHub,
    *paths: str,
) -> "Response":
    return await fetch_url_source(
        FileSourceURL(type="url", url=format_github_url(source)),
        *paths,
    )


async def fetch_source(source: FileSource, *paths: str) -> "Response":
    return await source_fetcher.get_from_type_or_instance(source)(source, *paths)

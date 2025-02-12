import asyncio
from collections.abc import Awaitable
from typing import TYPE_CHECKING, Any, Generic, Optional, Protocol, TypedDict, TypeVar
from typing_extensions import Unpack

from cookit import TypeDecoCollector, copy_func_arg_annotations, nullcontext
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
from .utils import op_retry

if TYPE_CHECKING:
    from httpx import Response

M = TypeVar("M", bound=FileSource)
M_contra = TypeVar("M_contra", bound=FileSource, contravariant=True)


class ReqKwargs(TypedDict, total=False):
    cli: Optional[AsyncClient]
    sem: Optional[asyncio.Semaphore]


class SourceFetcher(Protocol, Generic[M_contra]):
    def __call__(
        self,
        source: M_contra,
        *paths: str,
        **req_kw: Unpack[ReqKwargs],
    ) -> Awaitable["Response"]: ...


@copy_func_arg_annotations(AsyncClient)
def create_client(**kwargs):
    return AsyncClient(
        **{
            "proxy": config.proxy,
            "follow_redirects": True,
            **kwargs,
        },
    )


global_req_sem = asyncio.Semaphore(config.meme_stickers_req_concurrency)
source_fetcher = TypeDecoCollector[FileSource, SourceFetcher[Any]]()


@source_fetcher(FileSourceURL)
async def fetch_url_source(
    source: FileSourceURL,
    *paths: str,
    cli: Optional[AsyncClient] = None,
    sem: Optional[asyncio.Semaphore] = None,
) -> "Response":
    url = str(URL(source.url).joinpath(*paths))

    @op_retry(f"Fetch {url} failed")
    async def fetch(cli: AsyncClient) -> "Response":
        return (await cli.get(url)).raise_for_status()

    ctx = create_client() if cli is None else nullcontext(cli)
    sem = global_req_sem if sem is None else sem
    async with sem, ctx as ctx_cli:
        return await fetch(ctx_cli)


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
    **req_kw: Unpack[ReqKwargs],
) -> "Response":
    return await fetch_url_source(
        FileSourceURL(type="url", url=format_github_url(source)),
        *paths,
        **req_kw,
    )


async def fetch_source(
    source: FileSource,
    *paths: str,
    **req_kw: Unpack[ReqKwargs],
) -> "Response":
    return await source_fetcher.get_from_type_or_instance(
        source,
    )(source, *paths, **req_kw)

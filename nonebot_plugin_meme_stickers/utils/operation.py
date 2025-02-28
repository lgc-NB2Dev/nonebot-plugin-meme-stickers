from dataclasses import dataclass, field
from typing import Any, Callable, Generic, Optional, TypeVar
from typing_extensions import override

from cookit import TypeDecoCollector

from . import format_error

T = TypeVar("T")
T2 = TypeVar("T2")


@dataclass
class OpIt(Generic[T]):
    value: T
    info: Optional[str] = None
    exc: Optional[BaseException] = None


@dataclass
class OpInfo(Generic[T]):
    succeed: list[OpIt[T]] = field(default_factory=list)
    failed: list[OpIt[T]] = field(default_factory=list)
    skipped: list[OpIt[T]] = field(default_factory=list)

    def format(self) -> str:
        return format_op(self)


OpValFormatter = Callable[[T], str]


class OpValFormatterDeco(TypeDecoCollector[T, OpValFormatter[T]]):
    @override
    def __call__(
        self,
        key: type[T2],
    ) -> Callable[[OpValFormatter[T2]], OpValFormatter[T2]]:
        return super().__call__(key)  # type: ignore


op_val_formatter = OpValFormatterDeco[Any]()
op_val_formatter(str)(lambda it: it)


def format_op_it(it: OpIt[Any]) -> str:
    val_formatter = op_val_formatter.get_from_type_or_instance(
        it.value,
        lambda x: str(x),
    )
    txt = [val_formatter(it.value)]
    if it.info:
        txt.append(it.info)
    if it.exc:
        txt.append(format_error(it.exc))
    return ": ".join(txt)


def format_op(op: OpInfo[Any]):
    txt: list[str] = []
    if op.succeed:
        txt.append(f"成功 ({len(op.succeed)} 个)：")
        txt.extend(f"  - {format_op_it(it)}" for it in op.succeed)
    if op.skipped:
        txt.append(f"跳过 ({len(op.skipped)} 个)：")
        txt.extend(f"  - {format_op_it(it)}" for it in op.skipped)
    if op.failed:
        txt.append(f"失败 ({len(op.failed)} 个)：")
        txt.extend(f"  - {format_op_it(it)}" for it in op.failed)
    return "\n".join(txt) if txt else "没有执行任何操作"

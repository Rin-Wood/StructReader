from io import BytesIO, BufferedReader
from struct import unpack_from as UnPack
from typing import Literal, Callable, Any

INT     = 1
FLOAT   = 2
UVARINT = 3
STR     = 4
BYTES   = 5
BYTES2  = 6
LIST    = 7
STRUCT  = 8
CONST   = 9
VAR     = 10
MATCH   = 11
FUNC    = 12
SEEK    = 13
POS     = 14
PEEK    = 15
GROUP   = 16
BOOL    = 17

class Struct:
    pass

class BaseType:
    __slots__ = ('Type', 'Name', 'Bits', 'Order', 'Sign', 'Len', 'Encoding', 'Count', 'Value', 'Params', 'BFunc', 'Results', 'Offset', 'Mode')

    def __init__(self, typeIndex, value = None):
        self.Type = typeIndex
        if typeIndex == INT:
            self.Bits, self.Order, self.Sign = value
        elif typeIndex == FLOAT:
            self.Bits, self.Order, self.Sign = value
        elif typeIndex == STR:
            if not isinstance(value, tuple):
                value = (value, None)
            self.Len, self.Encoding = value
        elif typeIndex == BYTES:
            self.Len = value
        elif typeIndex == VAR:
            self.Name = value
        elif typeIndex == LIST:
            self.Count, self.Value = value
        elif typeIndex == GROUP:
            value = list(value) if isinstance(value, tuple) else value if isinstance(value, list) else [value]
            self.Params = value
        elif typeIndex == FUNC:
            self.BFunc, params = value if isinstance(value[1], (list, tuple)) else (value[0], value[1:])
            self.Params = params if isinstance(params, BaseType) and params.Type == GROUP else BaseType(GROUP, params)
        elif typeIndex == MATCH:
            cond, params, self.Results = value
            self.BFunc = BaseType(FUNC, (cond, params))
        elif typeIndex == SEEK:
            if not isinstance(value, tuple):
                value = (value, 0)
            self.Offset, self.Mode = value[0], v if (v := value[1]) in (0, 1, 2) else 0
        elif typeIndex == PEEK:
            self.Value = value

class _TypeFactory:
    __slots__ = ('Type', 'Params')

    def __init__(self, tName: str):
        self.Params = []
        if tName.startswith(('Int', 'UInt')):
            self.Type = INT
            self.Params = ['big' if tName.endswith('BE') else 'Little' if tName.endswith('LE') else None, tName.startswith('Int')]
        elif tName.startswith('Float'):
            self.Type = FLOAT
            self.Params = ['>' if tName.endswith('BE') else '<' if tName.endswith('LE') else None]
        elif tName == 'Str':
            self.Type = STR
        elif tName == 'Bytes':
            self.Type = BYTES
        elif tName == 'List':
            self.Type = LIST
        elif tName == 'Match':
            self.Type = MATCH
        elif tName == 'Func':
            self.Type = FUNC
        elif tName == 'Group':
            self.Type = GROUP
        elif tName == 'Seek':
            self.Type = SEEK
        elif tName == 'Peek':
            self.Type = PEEK
        elif tName == 'Var':
            self.Type = VAR

    def __getitem__(self, args):
        if (p := self.Params):
            args = (args // 8, *p)
        return BaseType(self.Type, args)

    def __getattr__(self, name):
        if (t := self.Type) == VAR:
            return BaseType(t, name)
        raise AttributeError(f"AttributeError: '{t}' object has no attribute '{name}'")

def CompileType(v, order: str, order2: str, encoding: str, bytesToHex: bool):
    if isinstance(v, BaseType):
        if (t := v.Type) == VAR:
            return (t, v.Name)
        elif t == INT:
            return (t, v.Bits, v.Sign, v.Order or order)
        elif t == FLOAT:
            return (t, v.Bits, v.Sign, v.Order or order2)
        elif t == UVARINT:
            return (t,)
        elif t == POS:
            return (t,)
        elif t == BOOL:
            return (t,)
        elif t == SEEK:
            return (t, CompileType(v.Offset, order, order2, encoding, bytesToHex), v.Mode)
        elif t == PEEK:
            return (t, CompileType(v.Value, order, order2, encoding, bytesToHex))
        elif t == GROUP:
            return (t, [CompileType(i, order, order2, encoding, bytesToHex) for i in v.Params])
        elif t == FUNC:
            return (t, v.BFunc, CompileType(v.Params, order, order2, encoding, bytesToHex))
        elif t == MATCH:
            return (t, CompileType(v.BFunc, order, order2, encoding, bytesToHex), [CompileType(i, order, order2, encoding, bytesToHex) for i in v.Results])
        elif t == BYTES:
            return (BYTES2 if bytesToHex else BYTES, CompileType(v.Len, order, order2, encoding, bytesToHex))
        elif t == STR:
            return (t, CompileType(v.Len, order, order2, encoding, bytesToHex), v.Encoding or encoding)
        elif t == LIST:
            return (t, CompileType(v.Count, order, order2, encoding, bytesToHex), CompileType(v.Value, order, order2, encoding, bytesToHex))
    elif isinstance(v, (int, str)):
        return (CONST, v)
    elif isinstance(v, type):
        return (STRUCT, CompileStruct(v, order, encoding, order2, bytesToHex))
    else:
        raise TypeError(v)

def CompileStruct(cls: object, order: Literal['big', 'little'] = 'little', encoding: str = 'utf-8', order2: Literal['>', '<'] = None, bytesToHex: bool = False):
    if order2 is None:
        order2 = '>' if order == 'big' else '<'
    return {n:CompileType(v, order, order2, encoding, bytesToHex) for n, v in cls.__dict__.items() if not (n.startswith('__') and n.endswith('__'))}

class StructObj:
    __slots__ = ('FuncDict', 'Get', '_Ctx')

    def __init__(self):
        self.FuncDict = {INT:self.ParseInt, FLOAT:self.ParseFloat, UVARINT:self.ParseUvarint, STR:self.ParseStr, BYTES:self.ParseBytes,
                         BYTES2:self.ParseBytes2, LIST:self.ParseList, STRUCT:self.ParseStruct, CONST:self.ParseNumber, VAR:self.ParseVar,
                         MATCH:self.ParseMatch, GROUP:self.ParseGroup, FUNC:self.ParseFunc, SEEK:self.ParseSeek, PEEK:self.ParsePeek,
                         POS:self.ParsePos, BOOL:self.ParseBool}
        self.Get = self.FuncDict.get
        self._Ctx: dict[str, Any] = {}

    def Parse(self, struct: dict[str, Any], r: BufferedReader | bytes) -> object:
        ctx = self._Ctx
        obj, fd = Struct(), self.Get
        for n, v in struct.items():
            try:
                func = fd(v[0], None)
                assert func is not None
                ctx[n] = vv = func(r, v)
            except:
                raise RuntimeError(v)
            setattr(obj, n, vv)
        return obj

    def ParseInt(self, r: BufferedReader, params: tuple[int, int, bool, str]) -> int:
        _, size, signed, order = params
        return int.from_bytes(r.read(size), order, signed=signed)

    def ParseFloat(self, r: BufferedReader, params: tuple[int, int, str, str]) -> float:
        _, size, sign, order = params
        return UnPack(f'{order}{sign}', r.read(size))[0]

    def ParseStr(self, r: BufferedReader, params: tuple[int, tuple, str]) -> str:
        _, lenParams, encoding = params
        return r.read(self.Get(lenParams[0])(r, lenParams)).decode(encoding)

    def ParseBytes(self, r: BufferedReader, params: tuple[int, tuple]) -> str:
        _, lenParams = params
        return r.read(self.Get(lenParams[0])(r, lenParams))

    def ParseBytes2(self, r: BufferedReader, params: tuple[int, tuple]) -> str:
        _, lenParams = params
        return r.read(self.Get(lenParams[0])(r, lenParams)).hex()

    def ParseNumber(self, r: BufferedReader, params: tuple[int, int]) -> str:
        _, number = params
        return number

    def ParseList(self, r: BufferedReader, params: tuple[int, tuple, tuple]) -> str:
        _, count, value = params
        loop, t = self.Get(count[0])(r, count), value[0]
        return [self.Get(t)(r, value) for _ in range(loop)]

    def ParseStruct(self, r: BufferedReader, params: tuple[int, dict[str, Any]]):
        return self.Parse(params[1], r)

    def ParseUvarint(self, r: BufferedReader, _):
        value, shift = 0, 0
        while True:
            b = r.read(1)
            if not b:
                raise EOFError
            byte = b[0]
            value |= (byte & 0x7F) << shift
            if not (byte & 0x80):
                return value
            shift += 7

    def ParseBool(self, r: BufferedReader, _):
        b = r.read(1)
        if not b:
            raise EOFError()
        return b[0] != 0

    def ParseVar(self, r: BufferedReader, params: tuple[int, str]):
        return self._Ctx[params[1]]

    def ParsePos(self, r: BufferedReader, _):
        return r.tell()

    def ParseGroup(self, r: BufferedReader, params: tuple[int, list]):
        _, cParams = params
        return [self.Get(i[0])(r, i) for i in cParams]

    def ParseFunc(self, r: BufferedReader, params: tuple[int, Callable, tuple]):
        _, func, cParams = params
        return func(*self.Get(cParams[0])(r, cParams))

    def ParseMatch(self, r: BufferedReader, params: tuple[int, tuple, list]):
        _, cond, cresults = params
        result = cresults[self.Get(cond[0])(r, cond)]
        return self.Get(result[0])(r, result)

    def ParseSeek(self, r: BufferedReader, params: tuple[int, tuple, int]) -> str:
        _, pos, mode = params
        r.seek(self.Get(pos[0])(r, pos), mode)
        return -1

    def ParsePeek(self, r: BufferedReader, params: tuple[int, tuple]) -> str:
        _, v = params
        pos = r.tell()
        vv = self.Get(v[0])(r, v)
        r.seek(pos)
        return vv

class StructDict(StructObj):
    def Parse(self, struct: dict[str, Any], r: BufferedReader | bytes) -> dict[str, Any]:
        ctx = self._Ctx
        obj, fd = {}, self.Get
        for n, v in struct.items():
            try:
                func = fd(v[0], None)
                assert func is not None
                ctx[n] = vv = func(r, v)
            except:
                raise RuntimeError(v)
            obj[n] = vv
        return obj

Int           = _TypeFactory('Int')
UInt          = _TypeFactory('UInt')
IntBE         = _TypeFactory('IntBE')
IntLE         = _TypeFactory('IntLE')
UIntBE        = _TypeFactory('UIntBE')
UIntLE        = _TypeFactory('UIntLE')
Float         = _TypeFactory('Float')
FloatBE       = _TypeFactory('FloatBE')
FloatLE       = _TypeFactory('FloatLE')
Str           = _TypeFactory('Str')
Bytes         = _TypeFactory('Bytes')
List          = _TypeFactory('List')
Match         = _TypeFactory('Match')
Seek          = _TypeFactory('Seek')
Peek          = _TypeFactory('Peek')
Func          = _TypeFactory('Func')
Group         = _TypeFactory('Group')
Uvarint       = BaseType(UVARINT)
Var           = _TypeFactory('Var')
Pos           = BaseType(POS)
Bool           = BaseType(BOOL)
StructObjCls  = StructObj()
StructDictCls = StructDict()
FuncObj       = StructObjCls.Parse
FuncDict      = StructDictCls.Parse

def ParseStruct(struct: object | dict[str, Any], r: BufferedReader | bytes, ReturnDict: bool = False, order: Literal['big', 'little'] = 'little', encoding: str = 'utf-8', order2: Literal['>', '<'] = None, bytesToHex: bool = False) -> object | dict[str, Any]:
    if isinstance(r, (bytes, bytearray, memoryview)):
        r = BytesIO(r)
    if isinstance(struct, type):
        struct = CompileStruct(struct, order, encoding, ('>' if order == 'big' else '<') if order2 is None else order2, bytesToHex)
    cls, func = (StructDictCls, FuncDict) if ReturnDict else (StructObjCls, FuncObj)
    cls._Ctx = {}
    v = func(struct, r)
    cls._Ctx = {}
    return v

__all__ = ['Int', 'UInt', 'IntBE', 'IntLE', 'UIntBE', 'UIntLE', 'Float', 'FloatBE', 'FloatLE', 'Str', 'List', 'Bytes', 'Uvarint', 'Var', 'Match', 'Pos', 'Seek', 'Peek', 'Func', 'Group', 'Bool', 'CompileStruct', 'ParseStruct']

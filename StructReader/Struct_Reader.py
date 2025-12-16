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
UNTIL   = 18
LEN     = 19
ALIGN   = 20

TypeDict = {'Str':STR, 'Bytes':BYTES, 'List':LIST, 'Match':MATCH, 'Func':FUNC, 'Group':GROUP, 'Seek':SEEK, 'Peek':PEEK, 'Var':VAR, 'Until':UNTIL, 'Align':ALIGN}
TypeDictGet = TypeDict.get

class Struct:
    pass

class BaseType:
    __slots__ = ('Type', 'Name', 'Bits', 'Order', 'Sign', 'Len', 'Encoding', 'Count', 'Value', 'Params', 'BFunc', 'Results', 'Offset', 'Mode')

    def __init__(self, typeIndex, value = None):
        self.Type = typeIndex
        if typeIndex == INT:
            self.Bits, self.Order, self.Sign = value
        elif typeIndex == FLOAT:
            self.Bits, self.Order = value
            self.Sign = 'f' if value[0] == 4 else 'd'
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
        elif typeIndex in (PEEK, UNTIL, ALIGN):
            if value is None and typeIndex in (UNTIL, ALIGN):
                value = b'\x00' if typeIndex == UNTIL else 16
            self.Value = value

class _TypeFactory:
    __slots__ = ('Type', 'Params')

    def __init__(self, tName: str):
        self.Params = []
        if (v := TypeDictGet(tName, None)) is not None:
            self.Type = v
        elif tName.startswith(('Int', 'UInt')):
            self.Type = INT
            self.Params = ['big' if tName.endswith('BE') else 'little' if tName.endswith('LE') else None, tName.startswith('Int')]
        elif tName.startswith('Float'):
            self.Type = FLOAT
            self.Params = ['>' if tName.endswith('BE') else '<' if tName.endswith('LE') else None]

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
        elif t == SEEK:
            return (t, CompileType(v.Offset, order, order2, encoding, bytesToHex), v.Mode)
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
        elif t in (PEEK, UNTIL, ALIGN):
            return (t, CompileType(v.Value, order, order2, encoding, bytesToHex))
        elif t in (UVARINT, POS, BOOL, LEN):
            return (t,)
        else:
            raise TypeError(v)
    elif isinstance(v, _TypeFactory):
        if (t := v.Type) == INT:
            o, sign = v.Params
            return (t, 4, sign, o or order)
        elif (t := v.Type) == FLOAT:
            return (t, 4, 'f', v.Params[0] or order2)
        elif t == SEEK:
            return (t, (CONST, 0), 0)
        elif t == STR:
            return (t, (INT, 1, False, order), encoding)
        elif t == BYTES:
            return (BYTES2 if bytesToHex else BYTES, (INT, 1, False, order))
        elif t in (UNTIL, ALIGN):
            return (t, (CONST, b'\x00') if t == UNTIL else (CONST, 16))
        else:
            raise TypeError(v)
    elif isinstance(v, (int, str, bytes)):
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
        self.FuncDict = {INT:self.ParseInt, FLOAT:self.ParseFloat, UVARINT:self.ParseUvarint, STR:self.ParseStr, BYTES:self.ParseBytes, BYTES2:self.ParseBytes2, LIST:self.ParseList, STRUCT:self.ParseStruct, CONST:self.ParseConst, VAR:self.ParseVar,
                         MATCH:self.ParseMatch, GROUP:self.ParseGroup, FUNC:self.ParseFunc, SEEK:self.ParseSeek, PEEK:self.ParsePeek, POS:self.ParsePos, BOOL:self.ParseBool, LEN:self.ParseLen, UNTIL:self.ParseUntil, ALIGN:self.ParseAlign}
        self.Get, self._Ctx = self.FuncDict.get, {}

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
        v = self.Get(lenParams[0])(r, lenParams)
        return v.decode(encoding) if lenParams[0] == UNTIL else r.read(v).decode(encoding)

    def ParseBytes(self, r: BufferedReader, params: tuple[int, tuple]) -> bytes:
        _, lenParams = params
        v = self.Get(lenParams[0])(r, lenParams)
        return v if lenParams[0] == UNTIL else r.read(v)

    def ParseBytes2(self, r: BufferedReader, params: tuple[int, tuple]) -> str:
        _, lenParams = params
        v = self.Get(lenParams[0])(r, lenParams)
        return v.hex() if lenParams[0] == UNTIL else r.read(v).hex()

    def ParseConst(self, r: BufferedReader, params: tuple[int, int | str | bytes]) -> int | str | bytes:
        return params[1]

    def ParseList(self, r: BufferedReader, params: tuple[int, tuple, tuple]) -> list[Any]:
        _, count, value = params
        loop, t = self.Get(count[0])(r, count), value[0]
        return [self.Get(t)(r, value) for _ in range(loop)]

    def ParseStruct(self, r: BufferedReader, params: tuple[int, dict[str, Any]]) -> object:
        return self.Parse(params[1], r)

    def ParseUvarint(self, r: BufferedReader, _) -> int:
        value, shift = 0, 0
        while True:
            if not (b := r.read(1)):
                raise EOFError
            byte = b[0]
            value |= (byte & 0x7F) << shift
            if not (byte & 0x80):
                return value
            shift += 7

    def ParseBool(self, r: BufferedReader, _) -> bool:
        b = r.read(1)
        if not b:
            raise EOFError()
        return b[0] != 0

    def ParseVar(self, r: BufferedReader, params: tuple[int, str]) -> Any:
        return self._Ctx[params[1]]

    def ParsePos(self, r: BufferedReader, _) -> int:
        return r.tell()

    def ParseGroup(self, r: BufferedReader, params: tuple[int, list]) -> list[Any]:
        _, cParams = params
        return [self.Get(i[0])(r, i) for i in cParams]

    def ParseFunc(self, r: BufferedReader, params: tuple[int, Callable, tuple]) -> Any:
        _, func, cParams = params
        return func(*self.Get(cParams[0])(r, cParams))

    def ParseMatch(self, r: BufferedReader, params: tuple[int, tuple, list]) -> Any:
        _, cond, cresults = params
        result = cresults[self.Get(cond[0])(r, cond)]
        return self.Get(result[0])(r, result)

    def ParseSeek(self, r: BufferedReader, params: tuple[int, tuple, int]) -> tuple[int, Literal[0, 1, 2]]:
        _, pos, mode = params
        r.seek((v := self.Get(pos[0])(r, pos)), mode)
        return (v, mode)

    def ParsePeek(self, r: BufferedReader, params: tuple[int, tuple]) -> str | int | bytes | bool | object | list:
        _, v = params
        pos = r.tell()
        vv = self.Get(v[0])(r, v)
        r.seek(pos)
        return vv

    def ParseLen(self, r: BufferedReader, _) -> int:
        pos = r.tell()
        r.seek(0, 2)
        pos2 = r.tell()
        r.seek(pos)
        return pos2

    def ParseUntil(self, r: BufferedReader, params: tuple[int, tuple]) -> bytes:
        _, v = params
        x = self.Get(v[0])(r, v)
        xLen = len(x)
        up = start = r.tell()
        while True:
            if not (b := r.read(xLen)):
                raise EOFError
            if b == x:
                break
            up += 1
            r.seek(up)
        pos = r.tell()
        r.seek(start)
        result = r.read(pos - start - xLen)
        r.seek(pos)
        return result

    def ParseAlign(self, r: BufferedReader, params: tuple[int, tuple]) -> int:
        _, v = params
        x = self.Get(v[0])(r, v)
        return (x - r.tell() % x) % x

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
Bool          = BaseType(BOOL)
Len           = BaseType(LEN)
Until         = _TypeFactory('Until')
Align         = _TypeFactory('Align')
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

__all__ = ['Int', 'UInt', 'IntBE', 'IntLE', 'UIntBE', 'UIntLE', 'Float', 'FloatBE', 'FloatLE', 'Str', 'List', 'Bytes', 'Uvarint', 'Var', 'Match', 'Pos', 'Seek', 'Peek', 'Func', 'Group', 'Bool', 'Len', 'Until', 'Align', 'CompileStruct', 'ParseStruct']

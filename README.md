# StructReader – Binary Structure Parsing Framework

## Installation
Install the latest version of `StructReader` from PyPI:

```bash
pip install StructReader
```

## 1. Overview

StructReader is a **binary format parsing framework** for Python.

It is designed specifically for **structured binary data parsing**, where the layout is known or partially known, such as custom file formats.

Instead of manually reading bytes and tracking offsets, you **declare the binary format structure**, and StructReader handles stream reading, endianness, field dependencies, and control flow.

---

## 2. Basic Idea

You define a binary structure as a **Python class**.

* Each class attribute represents one field
* The attribute value describes **how to read the field**

The framework:

1. Compiles the structure into an internal opcode representation
2. Executes the opcodes against a binary stream
3. Produces a Python object or dictionary

---

## 3. Defining a Structure

### Example

```python
class Header:
    magic = UIntBE[32]
    size  = UInt[16]
    data  = Bytes[size]
```

Parsing:

```python
obj = ParseStruct(Header, data)
```

Access fields:

```python
print(obj.magic)
print(obj.size)
print(obj.data)
```

---

## 4. Primitive Types

### 4.1 Integer Types

| Type        | Description              |
| ----------- | ------------------------ |
| `Int[n]`    | Signed integer, n bits   |
| `UInt[n]`   | Unsigned integer, n bits |
| `IntLE[n]`  | Little-endian signed     |
| `IntBE[n]`  | Big-endian signed        |
| `UIntLE[n]` | Little-endian unsigned   |
| `UIntBE[n]` | Big-endian unsigned      |

Example:

```python
id    = UInt[32]
flags = UIntBE[16]
```

---

### 4.2 Floating Point Types

| Type         | Description                        |
| ------------ | ---------------------------------- |
| `Float[n]`   | Floating point, default endianness |
| `FloatLE[n]` | Little-endian                      |
| `FloatBE[n]` | Big-endian                         |

Example:

```python
x = Float[32]
y = FloatBE[64]
```

---

### 4.3 Strings

```python
Str[length]
Str[length, encoding]
```

* `length` may be a constant or a previously defined field
* Default encoding is UTF-8

Example:

```python
name_len = UInt[8]
name     = Str[name_len]
```

---

### 4.4 Raw Bytes

```python
Bytes[length]
```

Reads raw bytes from the stream.

Example:

```python
payload = Bytes[16]
```

---

### 4.5 Variable-Length Integer

```python
Uvarint
```

Reads an unsigned variable-length integer using 7-bit continuation encoding.

---

## 5. Composite Types

### 5.1 List (Array)

```python
List[count, value_type]
```

* `count` may be a constant or another field

Example:

```python
count = UInt[16]
items = List[count, UInt[32]]
```

---

### 5.2 Nested Structures

Structures can be nested by referencing another structure class.

Example:

```python
class Point:
    x = Int[32]
    y = Int[32]

class Shape:
    center = Point
    radius = UInt[16]
```

---

## 6. Field References (Var)

```python
Var.field_name
```

Allows a field to reference a previously parsed field.

Example:

```python
class Packet:
    length = UInt[16]
    data   = Bytes[Var.length]
```

---

## 7. Stream Position Control

### 7.1 Current Position

```python
Pos
```

Returns the current read position in the stream.

---

### 7.2 Seek

```python
Seek[offset, mode]
```

| Mode | Meaning                      |
| ---- | ---------------------------- |
| `0`  | Absolute position            |
| `1`  | Relative to current position |
| `2`  | Relative to end              |

Example:

```python
Seek[128, 0]
```

---

### 7.3 Peek (Non-consuming Read)

```python
Peek[value]
```

Reads a value without advancing the stream position.

Example:

```python
next_type = Peek[UInt[8]]
```

---

## 8. Conditional Parsing (Match)

```python
Match[condition, results]
```

Selects one parsing branch based on the value of `condition`.

Example:

```python
class Entry:
    type = UInt[8]
    data = Match[
        type,
        (
            UInt[32],  # type == 0
            Str[8],    # type == 1
        )
    ]
```

---

## 9. Custom Functions (Func)

```python
Func[callable, params...]
```

Calls a Python function with parsed parameters.

Example:

```python
def checksum(a, b):
    return a ^ b

class Block:
    a = UInt[8]
    b = UInt[8]
    c = Func[checksum, a, b]
```

---

## 10. Group

```python
Group[param1, param2, ...]
```

Used to group multiple parameters, mainly for function calls.

---

## 11. Parsing API

### ParseStruct

```python
ParseStruct(struct, data,
            ReturnDict=False,
            order='little',
            encoding='utf-8',
            order2=None,
            bytesToHex=False)
```

#### Parameters

* `struct`

  * A structure class **or** a compiled structure dictionary

* `data`

  * `bytes`, `bytearray`, `memoryview`, or `BufferedReader`

* `ReturnDict` (bool)

  * `False` (default): return an object with attributes
  * `True`: return a dictionary

* `order` (`'little'` | `'big'`)

  * Default integer byte order

* `encoding` (str)

  * Default string encoding

* `order2` (`'<'` | `'>'` | None)

  * Float byte order override
  * If `None`, inferred from `order`

* `bytesToHex` (bool)

  * If `True`, `Bytes[...]` fields return hexadecimal strings

---

### Parse to Dictionary

```python
obj = ParseStruct(MyStruct, data, ReturnDict=True)
```

Returns a dictionary instead of an object.

---

### Input Data Types

The input stream may be:

* `bytes`
* `bytearray`
* `memoryview`
* `BufferedReader`

---

## 12. Error Handling

* Parsing errors raise `RuntimeError`
* The error contains the failing field definition
* Context (`Var`) is reset between parse calls

---

## 13. Design Advantages

* Explicit support for **binary format parsing**
* Declarative structure definitions
* Configurable endianness and encoding
* Field dependency via `Var`
* Conditional parsing (`Match`)
* Stream control (`Seek`, `Peek`, `Pos`)
* Object or dictionary output modes
* No external dependencies

---

## 14. Minimal Complete Example

```python
from StructReader import ParseStruct

class Example:
    a = UInt[16]
    b = UInt[16]

obj = ParseStruct(Example, b"\x00\x01\x00\x02")
print(obj.a, obj.b)
```

```python
from StructReader import CompileStruct, ParseStruct

class Example:
    a = UInt[16]
    b = UInt[16]

myStruct = CompileStruct(Example)
obj = ParseStruct(myStruct, b"\x00\x01\x00\x02")
print(obj.a, obj.b)
```

---

## 15. Summary

StructReader focuses on **binary format parsing** through a declarative, structure‑first approach.

By separating *format description* from *byte reading logic*, it allows complex binary layouts to be expressed clearly, maintained easily, and extended safely.

StructReader is especially suitable for projects involving:

* Complex or nested binary formats
* Field‑dependent layouts
* Conditional and dynamic parsing

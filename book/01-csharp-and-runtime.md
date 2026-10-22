# 01. C# and the .NET runtime: the fundamentals interviews test

## Why this chapter matters

Almost every .NET interview starts here. The screening round asks "value type or reference type?",
and the deep-dive round asks "why did this closure print 3 three times?". These questions look
simple, but they show quickly whether a candidate has a correct mental model of the runtime or only
memorized phrases. In real work the same model explains production bugs: a lost update from a
mutable dictionary key, a memory leak from an event subscription, a query that runs five times
because of deferred execution.

## What you will be able to do

- Explain where values live in memory, and why "structs live on the stack" is only partly true.
- Write correct equality (`Equals`, `GetHashCode`, `==`) and know when a `record` does it for you.
- Use nullable reference types, `required` and `init` the way Smartcat code does.
- Spot the classic traps: closure capture, multiple enumeration, `throw ex`, finalizers, boxing.
- Choose a collection by its complexity and by its read/write pattern (including `FrozenDictionary`).
- Answer follow-up questions at Senior and Staff depth, and ask them as an interviewer.

---

## Value types and reference types

**Concept.** A *value type* (`struct`, `enum`, primitives like `int`, `double`, `bool`, and
`record struct`) holds its data directly. A *reference type* (`class`, `record`, `interface`,
`delegate`, arrays, `string`) holds a reference (a pointer managed by the GC) to an object on the
managed heap.

Assignment copies the value. For a value type, the value *is* the data. For a reference type, the
value is the reference, so two variables point to the same object.

```csharp
public struct PointStruct { public int X; }
public class PointClass { public int X; }

var s1 = new PointStruct { X = 1 };
var s2 = s1;          // full copy
s2.X = 2;
Console.WriteLine(s1.X); // 1

var c1 = new PointClass { X = 1 };
var c2 = c1;          // copy of the reference
c2.X = 2;
Console.WriteLine(c1.X); // 2
```

**Why it matters.** Copy semantics decide whether a change is visible to other code. Most "my change
was lost" bugs with structs come from changing a copy.

```csharp
var points = new List<PointStruct> { new() { X = 1 } };
// points[0].X = 5;   // compile error CS1612: the indexer returns a copy
var p = points[0];
p.X = 5;              // changes the local copy only
points[0] = p;        // you must write it back
```

**Common mistake:** making a large struct (for example 64 bytes) "for performance". Every assignment,
parameter pass and return copies it. Microsoft guidance: use a struct when the type is small
(about 16 bytes or less), logically a single value, immutable, and not boxed often.

**Tip:** make structs `readonly struct`. The compiler then guarantees no field changes, and it can
avoid *defensive copies* (hidden copies the compiler makes when it calls a method on a struct
through a `readonly` field or an `in` parameter, because the method could change the struct).

```csharp
public readonly struct Money
{
	public Money(decimal amount, string currency)
	{
		Amount = amount;
		Currency = currency;
	}

	public decimal Amount { get; }
	public string Currency { get; }
}
```

### Passing by reference: `ref`, `out`, `in`

| Modifier | Must be set before call | Callee may write | Typical use |
|---|---|---|---|
| (none) | yes | writes a copy | normal case |
| `ref` | yes | yes, caller sees it | swap, in-place update of a big struct |
| `out` | no | must write | `TryParse`, `TryGetValue` |
| `in` | yes | no (read-only ref) | pass a big readonly struct without copy |

Do not confuse "reference type" with "passed by reference". A `List<int>` parameter is a reference
type passed *by value*: the callee gets a copy of the reference. It can change the list content,
but `list = new List<int>()` inside the callee does not affect the caller.

---

## Stack and heap (and why "structs live on the stack" is a simplification)

**Concept.** The interview phrase is: "value types live on the stack, reference types live on the
heap". The correct version is: **a value lives where its container lives**.

- A local variable of a value type is usually on the stack (or only in a CPU register).
- A value-type *field* of a class lives inside that class object, on the heap.
- An array of structs (`PointStruct[]`) is one heap object with the structs inline.
- A local captured by a lambda, or a local in an `async` / iterator method that lives across an
  `await` / `yield`, moves into a compiler-generated class on the heap.
- A boxed value type is a heap object.
- In the other direction: since .NET 9 and more in .NET 10, the JIT does *escape analysis* (it
  checks that an object never leaves the method) and can allocate some small reference-type objects
  on the stack.

```csharp
public class Order
{
	public Money Total;          // struct, stored inside the Order object on the heap
}

public static Func<int> MakeCounter()
{
	var count = 0;               // a value-type local...
	return () => ++count;        // ...captured, so it lives in a heap closure object
}
```

**Why it matters.** The stack/heap location is an implementation detail. The language contract is
about *copy semantics* and *lifetime*. An interviewer who asks this wants to hear that you know the
difference between the contract and the implementation.

**Common mistake:** saying "structs are faster because they are on the stack". They are faster only
when they avoid an allocation *and* are small enough that copying is cheap.

**Tip:** in an interview, give the short answer, then the correction: "Locals of value types usually
live on the stack; but the real rule is that a value lives inside its container; captured locals and
async locals move to the heap."

---

## Boxing and unboxing

**Concept.** *Boxing* converts a value type to `object` or to an interface it implements. The
runtime allocates a heap object and copies the value into it. *Unboxing* is the explicit cast back;
it checks the type and copies the value out.

```csharp
int number = 42;
object boxed = number;       // allocation + copy
int back = (int)boxed;       // type check + copy
// long wrong = (long)boxed; // InvalidCastException: unbox must use the exact type
```

Where boxing hides:

| Code | Boxes? | Why |
|---|---|---|
| `ArrayList.Add(5)` | yes | parameter is `object` |
| `List<int>.Add(5)` | no | generic, `T` is `int` |
| `IComparable c = 5;` | yes | interface conversion |
| `void M<T>(T x) where T : IComparable<T>` then `x.CompareTo(y)` | no | constrained call |
| `$"{count}"` in C# 10+ | no | interpolated string handlers avoid it |
| `string.Format("{0}", count)` | yes | parameter is `object` |
| `struct` used as a key in `Dictionary` without `IEquatable<T>` | yes, on every `Equals` | default `ValueType.Equals(object)` |

**Common mistake:** a struct with no `IEquatable<T>` and no `GetHashCode` override used as a
dictionary key. The default `ValueType.Equals` boxes and may use reflection over fields. It is slow
and creates garbage.

**Tip:** for value-type keys, use a `readonly record struct`. It implements `IEquatable<T>` and a
good `GetHashCode` for you.

```csharp
public readonly record struct SegmentKey(Guid DocumentId, int SegmentNumber);

var cache = new Dictionary<SegmentKey, string>();
cache[new SegmentKey(documentId, 7)] = "translated text";
```

---

## Strings: immutability and interning

**Concept.** `string` is a reference type, but it behaves like a value: it is *immutable*. Every
"change" creates a new string. `==` on two `string` variables compares content because `string`
overloads the operator.

```csharp
var a = "hello";
var b = string.Concat("hel", "lo".AsSpan()); // built at run time
Console.WriteLine(a == b);                      // True, content comparison
Console.WriteLine(ReferenceEquals(a, b));       // False, different objects
Console.WriteLine((object)a == (object)b);      // False, reference comparison
```

*Interning* means the runtime keeps one shared instance per distinct literal. All literals
`"hello"` in an assembly point to the same object. Strings built at run time are not interned
unless you call `string.Intern`, and interned strings stay in memory for the process lifetime.

**Why it matters.** Immutability makes strings safe to share between threads and safe as dictionary
keys. The cost is allocations in loops.

```csharp
// BAD: O(n^2) copying, n allocations
var result = "";
foreach (var segment in segments)
	result += segment.Text;

// GOOD
var builder = new StringBuilder();
foreach (var segment in segments)
	builder.Append(segment.Text);
var text = builder.ToString();

// ALSO GOOD for a known sequence
var joined = string.Join(" ", segments.Select(segment => segment.Text));
```

**Common mistake:** comparing user input with `ToLower() == "value"`. It allocates and it is
culture-sensitive (the Turkish "I" problem). Use
`string.Equals(input, "value", StringComparison.OrdinalIgnoreCase)`. For dictionary keys use
`StringComparer.OrdinalIgnoreCase`.

**Tip:** for identifiers, codes, file extensions and protocol values, use `Ordinal` or
`OrdinalIgnoreCase`. Use culture-aware comparison only for text that you show to humans and sort.
This is relevant for a translation platform: language codes such as `en-US` are protocol values, not
human text.

---

## Equality: `==`, `Equals`, `GetHashCode`

**Concept.** .NET has two kinds of equality:

- *Reference equality*: the same object (`ReferenceEquals`, default `==` for classes).
- *Value equality*: the same content (`Equals` override, `IEquatable<T>`, records, `string`).

`==` is an operator resolved at **compile time** from the static types. `Equals` is a virtual method
resolved at **run time**. They can give different answers.

```csharp
object x = "abc";
object y = string.Concat("ab", "c".AsSpan());
Console.WriteLine(x == y);       // False: object == object is reference comparison
Console.WriteLine(x.Equals(y));  // True: string.Equals override runs
```

**The `GetHashCode` contract:**

1. If `a.Equals(b)` is true, then `a.GetHashCode() == b.GetHashCode()` **must** be true.
2. Equal hash codes do **not** mean equal objects (collisions are allowed).
3. The hash code must not change while the object is a key in a hash-based collection.

Break rule 1 and `Dictionary` / `HashSet` lose items: they look in the wrong bucket. Break rule 3
(mutable key) and the item becomes impossible to find or remove.

```csharp
public sealed class LanguagePair : IEquatable<LanguagePair>
{
	public LanguagePair(string source, string target)
	{
		Source = source;
		Target = target;
	}

	public string Source { get; }
	public string Target { get; }

	public bool Equals(LanguagePair? other) =>
		other is not null
		&& string.Equals(Source, other.Source, StringComparison.OrdinalIgnoreCase)
		&& string.Equals(Target, other.Target, StringComparison.OrdinalIgnoreCase);

	public override bool Equals(object? obj) => Equals(obj as LanguagePair);

	public override int GetHashCode() => HashCode.Combine(
		StringComparer.OrdinalIgnoreCase.GetHashCode(Source),
		StringComparer.OrdinalIgnoreCase.GetHashCode(Target));
}
```

Note that the hash uses the same case-insensitive rule as `Equals`. If `Equals` ignores case but
`GetHashCode` does not, rule 1 breaks.

**Common mistake:** a mutable key.

```csharp
var key = new MutableKey { Id = 1 };
var set = new HashSet<MutableKey> { key };
key.Id = 2;                      // hash code changes
Console.WriteLine(set.Contains(key)); // False, item is "lost" inside the set
```

**Tip:** if you override `Equals`, override `GetHashCode` too (the compiler warns, and with
`TreatWarningsAsErrors` the build fails). Make the type immutable, or use a record.

---

## Records, `init` and `required`

**Concept.** A `record` (C# 9) is a class with compiler-generated value equality, `ToString`,
deconstruction and non-destructive mutation through `with`. A `record struct` (C# 10) is the same
for value types.

```csharp
public sealed record TranslationRequest(Guid DocumentId, string TargetLanguage);

var first = new TranslationRequest(documentId, "de");
var second = first with { TargetLanguage = "fr" };   // new object, first is unchanged
Console.WriteLine(first == new TranslationRequest(documentId, "de")); // True
```

What a record compares: all instance fields, plus an `EqualityContract` (the run-time type), so a
base record and a derived record with the same values are not equal.

**Trap: equality is shallow.** A `List<string>` property is compared by reference.

```csharp
public sealed record Batch(string Name, List<string> Items);

var one = new Batch("a", new List<string> { "x" });
var two = new Batch("a", new List<string> { "x" });
Console.WriteLine(one == two); // False: two different List objects
```

`with` is also shallow: the copy shares the same list. If you need value semantics for a collection
inside a record, use an immutable collection and write `Equals` yourself, or keep collections out of
equality-sensitive records.

**`init` accessors** (C# 9) let a property be set only during object initialization.
**`required` members** (C# 11) force the caller to set them in the object initializer. The compiler
checks it.

```csharp
public sealed class ExportSettings
{
	public required string Format { get; init; }
	public required Guid AccountId { get; init; }
	public int MaxFileSizeMb { get; init; } = 100;
}

var settings = new ExportSettings { Format = "xliff", AccountId = accountId };
// var broken = new ExportSettings { Format = "xliff" }; // error CS9035: AccountId is required
```

`required` is about *being set*, not about *being non-null*. A `required Guid? ProjectId` must be
written by the caller, but `null` is a valid value. This is useful: it forces every caller to make a
decision, even when the decision is "no project".

A constructor that sets all required members can tell the compiler with
`[SetsRequiredMembers]`. Use it carefully: the compiler then trusts you.

**Common mistake:** `{ get; set; }` on everything "because the serializer needs it". Modern
serializers (`System.Text.Json`, the MongoDB C# driver) work with `init` setters.

### At Smartcat: `required` + `init` on models

The Smartcat code style (`backend-smartcat-codestyle`) says: **Mongo models use `required` + `init`
for mandatory fields**, with `[BsonElement("camelCase")]`, `[BsonRequired]` for non-nullable fields
and `[BsonIgnoreIfDefault]` for optional ones. The `review-dotnet-style` rule D16 flags a public
`{ get; set; }` on a Mongo-mapped class as MINOR, and recommends factory methods for changes.

```csharp
public sealed class TranslationJobDocument
{
	[BsonId, BsonRequired]
	public required ObjectId Id { get; init; }

	[BsonElement("accountId"), BsonRequired]
	public required Guid AccountId { get; init; }

	[BsonElement("status"), BsonRepresentation(BsonType.String)]
	public required TranslationJobStatus Status { get; init; }

	[BsonElement("comment"), BsonIgnoreIfNull]
	public string? Comment { get; init; }
}
```

A real example is `smartcat/Features/Cat/Core.Contract/Progress/Models/DocumentStageUserProgress.cs`:
it uses `required` together with nullable types (`required Guid? ProjectId { get; init; }`), exactly
the "must be set, may be null" case.

Contracts and DTOs are different: the style guide says request DTOs have no constructors, public
setters and no attributes. Config classes use `required` + `init`. Rule D6 also recommends a
`sealed record` for objects passed across `await` boundaries, so nobody changes them in the middle
of an async flow.

---

## Nullable reference types (NRT)

**Concept.** With `<Nullable>enable</Nullable>` (or `#nullable enable` in a file), `string` means
"not null" and `string?` means "may be null". The compiler does *flow analysis* and warns when you
may dereference null or assign null to a non-nullable variable.

It is a **compile-time** feature only. At run time `string` and `string?` are the same type. A
caller with NRT disabled, a deserializer, or reflection can still give you `null`.

```csharp
#nullable enable

public sealed class SegmentFormatter
{
	public string Format(string text, string? comment)
	{
		if (comment is null)
			return text;

		return $"{text} ({comment.Trim()})";   // no warning: flow analysis knows comment is not null
	}
}
```

Useful tools:

| Tool | Meaning |
|---|---|
| `x!` (null-forgiving) | "I know it is not null". Silences the warning, adds no check. |
| `default!` | initialize a non-nullable field that is set later (for example by a framework) |
| `[NotNullWhen(true)]` | on an `out` parameter of a `TryGet` method |
| `[MaybeNullWhen(false)]` | the `out` value may be null when the method returns false |
| `[MemberNotNull(nameof(_x))]` | this method guarantees `_x` is set |
| `ArgumentNullException.ThrowIfNull(x)` | run-time guard on public API boundaries |

```csharp
public bool TryGetTranslation(string key, [NotNullWhen(true)] out string? translation)
{
	return _translations.TryGetValue(key, out translation);
}
```

**Common mistake:** using `!` to make warnings go away. Each `!` is a claim that the compiler cannot
check. In review, ask "why is this not null here?" for every `!` in new code.

**Tip:** NRT protects you inside your code. At the boundaries (public API, deserialized input,
legacy callers) still validate.

### At Smartcat: NRT per file in the monolith, per project in services

- In the monolith, NRT is **not** enabled project-wide. The style guide says: add `#nullable enable`
  at the top of new files (there are well over a thousand such files in `smartcat/Features`), and
  when you change an old file you may use `#nullable restore` around the new code.
- Newer services such as `project-tasks-service` and `smartcat-ai-agents` set
  `<Nullable>enable</Nullable>` in `Directory.Build.props`.
- All of them use `TreatWarningsAsErrors=true`. So a nullable warning is a build error. The
  `review-dotnet-style` anchor says it directly: "If something nullable-related compiles, it is
  correct". The review then focuses on `!` and on boundaries, not on the warnings.

---

## Generics: constraints and variance

**Concept.** Generics give type safety without boxing. The runtime creates one shared
implementation for all reference-type arguments and a specialized one for each value-type argument.
That is why `List<int>` has no boxing.

### Constraints

| Constraint | Meaning |
|---|---|
| `where T : class` / `class?` | reference type |
| `where T : struct` | non-nullable value type |
| `where T : notnull` | any non-nullable type |
| `where T : unmanaged` | value type with no references inside (can be used with pointers, `stackalloc`) |
| `where T : new()` | has a public parameterless constructor |
| `where T : SomeBase` | derives from the class |
| `where T : IComparable<T>` | implements the interface |
| `where T : allows ref struct` (C# 13) | the type argument may be a `ref struct` such as `Span<T>` |

```csharp
public static T MaxBy<T>(IReadOnlyList<T> items) where T : IComparable<T>
{
	if (items.Count == 0)
		throw new ArgumentException("Empty list", nameof(items));

	var max = items[0];
	for (var index = 1; index < items.Count; index++)
	{
		if (items[index].CompareTo(max) > 0)
			max = items[index];
	}

	return max;
}
```

Since C# 11, interfaces can have `static abstract` members. That enables *generic math*
(`INumber<T>`): one `Sum<T>` method works for `int`, `decimal` and `double`.

### Variance: `out` and `in`

- **Covariance (`out T`)**: you can use a more derived type where a less derived one is expected.
  `IEnumerable<string>` is an `IEnumerable<object>`. Allowed only when `T` appears in output
  positions.
- **Contravariance (`in T`)**: the opposite. `Action<object>` can be used as `Action<string>`;
  `IComparer<object>` as `IComparer<string>`. Allowed only when `T` is in input positions.
- **Invariance**: `List<T>` is neither. `List<string>` is not a `List<object>`, because `List<T>`
  both reads and writes `T`.

```csharp
IEnumerable<string> names = new List<string> { "a" };
IEnumerable<object> objects = names;            // OK, covariance

Action<object> log = value => Console.WriteLine(value);
Action<string> logString = log;                 // OK, contravariance

// List<object> list = new List<string>();      // compile error, invariant
```

Rules: variance works only on **interfaces and delegates**, and only for **reference-type**
arguments. `IEnumerable<int>` is not `IEnumerable<object>`.

**Trap: array covariance.** Arrays were covariant before generics existed, and this is not
type-safe:

```csharp
object[] items = new string[1];
items[0] = 42;   // compiles, throws ArrayTypeMismatchException at run time
```

**Tip:** a good way to remember: `out` = "comes out of the interface" (return values), `in` = "goes
into the interface" (parameters).

---

## Delegates, events, lambdas and closures

**Concept.** A *delegate* is a type-safe reference to a method (plus a target object for instance
methods). Delegates are *multicast*: `+=` builds an invocation list. `Func<>`, `Action<>` and
`Predicate<T>` are the standard generic delegates.

An *event* is a delegate field with restricted access: outside code can only `+=` and `-=`; only the
owning class can invoke it or replace it.

```csharp
public sealed class DocumentImporter
{
	public event EventHandler<DocumentImportedEventArgs>? DocumentImported;

	public void Import(Document document)
	{
		// ... import ...
		DocumentImported?.Invoke(this, new DocumentImportedEventArgs(document.Id));
	}
}
```

`?.Invoke` reads the field once, so it is safe if another thread unsubscribes between the check and
the call.

**Memory leak:** the publisher holds a reference to every subscriber through the delegate. A
long-lived publisher (a singleton, a static event) keeps short-lived subscribers alive forever if
they never unsubscribe.

```csharp
public sealed class EditorSession : IDisposable
{
	private readonly DocumentImporter _importer;   // a singleton

	public EditorSession(DocumentImporter importer)
	{
		_importer = importer;
		_importer.DocumentImported += onImported;
	}

	public void Dispose() => _importer.DocumentImported -= onImported;   // without this, a leak

	private void onImported(object? sender, DocumentImportedEventArgs args) { /* ... */ }
}
```

### Closures and the capture trap

A *closure* is a lambda that uses a variable from the outer scope. The compiler moves the variable
into a generated class (a "display class"), and the lambda and the method share **the same
variable**, not a copy of its value.

```csharp
var actions = new List<Action>();
for (var i = 0; i < 3; i++)
	actions.Add(() => Console.Write(i));

foreach (var action in actions)
	action();          // prints 333
```

There is one `i` for the whole `for` loop, and when the actions run, it is 3. `foreach` is different
since C# 5: each iteration gets a new variable, so the same code with `foreach` prints `012`.

```csharp
for (var i = 0; i < 3; i++)
{
	var copy = i;      // new variable per iteration
	actions.Add(() => Console.Write(copy));
}
```

Other consequences of capture:

- Allocation: every capture creates a heap object. In hot paths this matters.
- Lifetime: a captured `this` or a large object lives as long as the delegate lives.
- Thread safety: two lambdas running on different threads share the captured variable.

**Tip:** `static` lambdas (C# 9) cannot capture anything. The compiler stops accidental captures.

```csharp
var ids = documents.Select(static document => document.Id);
```

### At Smartcat: closures and identity across pods

`review-architecture` rule A3 flags lambdas and `Func<>` instances used as workflow node identity in
`smartcat-ai-agents`: a closure is a new object on each pod, so its identity is not stable across
pods. Use stable `Name` / `Id` strings. This is the same capture lesson at the distributed level.

---

## LINQ: deferred execution, multiple enumeration, `IEnumerable` vs `IQueryable`

**Concept.** Most LINQ operators (`Where`, `Select`, `OrderBy`, `Take`) are *deferred*: they build a
pipeline and do nothing until you enumerate it. Operators that return a single value or a new
collection (`ToList`, `ToArray`, `Count`, `First`, `Any`, `Sum`) run the pipeline *immediately*.

```csharp
var threshold = 10;
var query = numbers.Where(number => number > threshold);  // nothing runs yet
threshold = 100;
var result = query.ToList();     // runs now, with threshold = 100
```

### Multiple enumeration

Each enumeration runs the whole pipeline again. If the source is a database query, an HTTP stream or
an expensive `Select`, you pay several times. If the source changes, the results can differ.

```csharp
// BAD: the query runs twice (and can return different data each time)
IEnumerable<Segment> untranslated = repository.QuerySegments().Where(segment => !segment.IsConfirmed);
if (untranslated.Any())
	logger.LogInformation("Untranslated: {Count}", untranslated.Count());

// GOOD
var untranslatedList = repository.QuerySegments().Where(segment => !segment.IsConfirmed).ToList();
if (untranslatedList.Count > 0)
	logger.LogInformation("Untranslated: {Count}", untranslatedList.Count);
```

**Tip:** accept `IEnumerable<T>` only when you enumerate once. If you need to enumerate several times
or need `Count`, accept `IReadOnlyCollection<T>` or `IReadOnlyList<T>` and let the caller
materialize.

### `IEnumerable<T>` vs `IQueryable<T>`

| | `IEnumerable<T>` | `IQueryable<T>` |
|---|---|---|
| Lambdas compiled to | delegates (`Func<T, bool>`) | expression trees (`Expression<Func<T, bool>>`) |
| Runs where | in process memory | translated by a provider (EF Core, MongoDB driver) |
| Unknown method in a lambda | just runs | provider cannot translate it, usually throws |
| Filtering | after all rows are loaded | in the database |

```csharp
// The filter runs in MongoDB
var active = collection.AsQueryable().Where(job => job.Status == JobStatus.Active).ToList();

// AsEnumerable switches to in-memory: everything after it runs in your process
var all = collection.AsQueryable().AsEnumerable().Where(job => job.Status == JobStatus.Active).ToList();
```

**Common mistake:** a repository method returns `IEnumerable<T>` built from an `IQueryable<T>`, and
the caller adds `.Where(...)`. The extra filter runs in memory after the full collection was loaded.
`review-architecture` rule A21 ("unbounded full-collection scan") flags the result of this.

**Small rules that reviewers flag** (`review-dotnet-style` D9): use `Any(predicate)` instead of
`Where(predicate).Any()`, and `Any()` instead of `Count() > 0`. `Count()` on a non-collection
enumerates everything; `Any()` stops at the first item.

### At Smartcat: lambdas and Mongo reads

- Lambda parameter names: `projectCosts.Sum(pc => pc.Amount)`, not `_ => _.Amount`. The underscore
  is only for a parameter that is not used (`backend-smartcat-codestyle`).
- Mongo filters: always typed (`Builders<T>.Filter` or a lambda), never hand-built BSON for Guids,
  because Smartcat stores `Guid` in the legacy C# binary format (`smartcat/.claude/rules/mongo.md`).
  A typed filter is LINQ-style expression translation, the `IQueryable` idea in practice.

---

## Exceptions

### `throw` vs `throw ex`

```csharp
try
{
	await importer.ImportAsync(file, cancellationToken);
}
catch (IOException exception)
{
	logger.LogError(exception, "Import failed for {FileId}", file.Id);
	throw;            // GOOD: keeps the original stack trace
	// throw exception; // BAD: the stack trace now starts here
}
```

`throw ex` resets the stack trace to the current line, so you lose where the error really happened.
If you must rethrow later (for example after collecting it on another thread), use
`ExceptionDispatchInfo.Capture(exception).Throw()`. To add context, wrap it:
`throw new ImportException("...", exception)` keeps the original as `InnerException`.

### Exception filters (`when`)

```csharp
catch (HttpRequestException exception) when (exception.StatusCode == HttpStatusCode.NotFound)
{
	return null;
}
```

A filter runs **before** the stack unwinds. If it returns false, the runtime continues searching
for another handler as if this `catch` did not exist. Benefits: the original stack is untouched
(better crash dumps), and you avoid catch-and-rethrow. A known trick is logging without catching:

```csharp
catch (Exception exception) when (logAndReturnFalse(exception))
{
	// never runs
}
```

### Exceptions as control flow

Exceptions are expensive (stack trace capture, unwinding) and they hide the normal flow. Use them
for *exceptional* conditions, not for expected outcomes.

```csharp
// BAD: rule D8 at Smartcat, "exception as success indicator" (MAJOR)
public bool IsValidLanguage(string code)
{
	try
	{
		CultureInfo.GetCultureInfo(code);
		return true;
	}
	catch (CultureNotFoundException)
	{
		return false;
	}
}

// GOOD: a Try method (or a Result type)
public bool TryGetProject(Guid id, [NotNullWhen(true)] out Project? project)
{
	return _projects.TryGetValue(id, out project);
}
```

Other rules:

- Catch the most specific type you can handle. `catch (Exception)` is fine at a boundary (a
  controller filter, a background loop, a message handler) where you log and decide.
- Do not swallow `OperationCanceledException` as an error. It is the normal result of cancellation.
- Never `catch { }` with an empty body.

### At Smartcat: exceptions in message handlers

In Kafka handlers the exception type is a decision. From `backend-modulehosting-events`: a
`ValidationException` is logged and skipped, a `TransientException` is retried and then goes to the
DLQ (dead-letter queue: a store for messages that failed), other exceptions go to the DLQ
immediately. Wrap failures in `EventHandlerException(responsibleTeams, e)` so the alert reaches the
right team. See chapter 07 (Domain events, the Outbox pattern and Kafka).

---

## `IDisposable`, `using` and `IAsyncDisposable`

**Concept.** The GC frees memory, not other resources: file handles, sockets, database connections,
locks. `IDisposable.Dispose` releases them *deterministically* (at a known moment).

```csharp
// using declaration (C# 8): Dispose runs at the end of the scope
using var stream = File.OpenRead(path);
using var reader = new StreamReader(stream);
var content = await reader.ReadToEndAsync(cancellationToken);
```

`using` compiles to `try/finally`, so `Dispose` runs even when an exception is thrown.

For resources whose cleanup is I/O (flushing a buffer to network, closing a connection gracefully),
implement `IAsyncDisposable` and use `await using`:

```csharp
await using var writer = new BlobWriter(storage, fileId);
await writer.WriteAsync(chunk, cancellationToken);
// DisposeAsync flushes and closes without blocking a thread
```

**Ownership rule:** dispose what you create; do not dispose what you were given. A class that
receives an `HttpClient` or a `Stream` through its constructor usually does not own it. In DI, the
container disposes the services it created at the end of their lifetime (scope end or app shutdown).

**Common mistakes:**

- `new HttpClient()` per request and disposing it. The sockets stay in `TIME_WAIT` and you can run
  out of ports. Use `IHttpClientFactory` or one long-lived client (see chapter 05, ASP.NET Core).
- Returning a stream from inside a `using` block: the caller gets a disposed stream.
- Forgetting that `Dispose` must be safe to call more than once.

### The Dispose pattern and finalizers

A *finalizer* (`~ClassName()`) runs on the finalizer thread when the GC finds the object
unreachable. You need one **only** if the class directly owns an unmanaged resource (a raw handle).
In modern code, wrap the handle in a `SafeHandle` instead; then you never write a finalizer.

```csharp
public class NativeBuffer : IDisposable
{
	private IntPtr _buffer = Marshal.AllocHGlobal(_bufferSize);
	private bool _disposed;

	~NativeBuffer() => Dispose(disposing: false);

	public void Dispose()
	{
		Dispose(disposing: true);
		GC.SuppressFinalize(this);   // the finalizer no longer needs to run
	}

	protected virtual void Dispose(bool disposing)
	{
		if (_disposed)
			return;

		if (disposing)
		{
			// release managed resources (other IDisposable fields) here
		}

		Marshal.FreeHGlobal(_buffer);   // release the unmanaged resource in both paths
		_buffer = IntPtr.Zero;
		_disposed = true;
	}

	private const int _bufferSize = 4096;
}
```

Why `disposing` matters: in the finalizer path, other managed objects may already be finalized, so
you must not touch them.

**Tip:** for a `sealed` class without unmanaged resources, a plain `Dispose()` that disposes its
fields is enough. No finalizer, no `Dispose(bool)`.

---

## Garbage collection

**Concept.** The .NET GC is *generational*, *compacting* and *tracing*. It starts from *roots*
(static fields, locals on thread stacks, CPU registers, GC handles) and marks everything reachable.
Everything else is garbage.

| Area | What goes there | Collected |
|---|---|---|
| Gen 0 | new small objects | very often, cheap |
| Gen 1 | survivors of gen 0, a buffer | often |
| Gen 2 | long-lived objects | rarely, expensive (full GC) |
| LOH (large object heap) | objects of 85,000 bytes or more | with gen 2; not compacted by default |
| POH (pinned object heap, .NET 5+) | objects allocated as pinned | with gen 2 |

The idea behind generations: most objects die young. Collecting only gen 0 is fast because it is
small.

**LOH problems:** large arrays (for example a `byte[]` for a whole file) go to the LOH. They are
collected only in gen 2 and the LOH is not compacted by default, so it can fragment. A service that
reads whole uploaded files into memory creates LOH pressure and full GCs. Prefer streaming and
`ArrayPool<T>.Shared`.

**GC modes:**

- *Workstation* GC: for desktop apps, one heap.
- *Server* GC: one heap per core, higher throughput, more memory. ASP.NET Core uses it by default.
- *Background* (concurrent) GC: gen 2 runs mostly while the app threads keep running.
- *DATAS* (dynamic adaptation to application sizes): on by default with Server GC since .NET 9; it
  changes the heap count with the load, which reduces memory in containers.

**Finalizers and the GC:** an object with a finalizer survives at least one extra collection. The GC
puts it on a queue, the finalizer thread runs it, and only the next collection frees the memory. So
finalizers make objects live longer and promote them to older generations. That is why
`GC.SuppressFinalize` in `Dispose` matters.

**Common mistakes:**

- Calling `GC.Collect()` in production code. It almost always makes things worse.
- Thinking a memory leak is impossible in .NET. Leaks are references you forgot: static
  collections that only grow, event subscriptions, caches with no limit, captured closures.

**Tip:** in an interview, connect GC to design: "We stream files instead of loading them into a
`byte[]`, because large buffers go to the LOH and cause gen 2 collections."

### At Smartcat: large payloads

`review-security` rule S22 flags file serving or proxying that loads the entire body into memory
(MAJOR, DoS and out-of-memory risk). `smartcat/.claude/rules/mongo.md` warns about unbounded arrays
in Mongo documents. Both are the same lesson as the LOH: keep memory per request bounded.

---

## `Span<T>` and `Memory<T>`

**Concept.** `Span<T>` is a view over contiguous memory: part of an array, a `stackalloc` buffer,
native memory or a string (`ReadOnlySpan<char>`). Slicing a span does not copy and does not
allocate.

`Span<T>` is a `ref struct`: it can live only on the stack. So it cannot be a field of a class, it
cannot be boxed, it cannot be captured by a lambda, and it cannot be alive across an `await`.
`Memory<T>` is the heap-friendly version: you can store it in a field and pass it through async
code, then call `.Span` when you need to work with the data.

```csharp
public static bool TryParseSegmentKey(ReadOnlySpan<char> input, out int documentNumber, out int segmentNumber)
{
	documentNumber = 0;
	segmentNumber = 0;

	var separator = input.IndexOf(':');
	if (separator < 0)
		return false;

	return int.TryParse(input[..separator], out documentNumber)
		&& int.TryParse(input[(separator + 1)..], out segmentNumber);
}

// No Substring, no allocations:
TryParseSegmentKey("12:345", out var document, out var segment);
```

```csharp
public async Task<int> CopyAsync(Stream source, Stream target, CancellationToken cancellationToken)
{
	var buffer = ArrayPool<byte>.Shared.Rent(_chunkSize);
	try
	{
		var total = 0;
		int read;
		while ((read = await source.ReadAsync(buffer.AsMemory(0, _chunkSize), cancellationToken)) > 0)
		{
			await target.WriteAsync(buffer.AsMemory(0, read), cancellationToken);
			total += read;
		}

		return total;
	}
	finally
	{
		ArrayPool<byte>.Shared.Return(buffer);
	}
}
```

Note: `Rent` can return a larger array than requested, so always use the length you asked for.

**Common mistake:** using `Span<T>` everywhere. It is a tool for hot paths (parsers, serializers,
buffers). In business code, readable code is worth more than avoiding one small allocation.

**Tip:** `stackalloc` is fine for small, bounded sizes (for example up to a few hundred bytes). A
large or user-controlled size can cause a `StackOverflowException`, which you cannot catch.

---

## Pattern matching

**Concept.** Pattern matching tests a value against a shape and extracts data in one step.

```csharp
public static string Describe(object value) => value switch
{
	null => "nothing",
	int count when count < 0 => "negative",
	int count => $"number {count}",
	string { Length: 0 } => "empty text",
	string text => $"text of {text.Length} chars",
	Project { Status: ProjectStatus.Completed } project => $"completed project {project.Name}",
	IEnumerable<int> numbers => $"{numbers.Count()} numbers",
	_ => "unknown",
};
```

| Pattern | Example | Since |
|---|---|---|
| type | `x is Project project` | C# 7 |
| constant / null | `x is null`, `x is not null` | C# 7 / 9 |
| property | `x is { Status: Active, Owner.Id: var ownerId }` | C# 8 / 10 |
| relational, logical | `x is > 0 and < 100` | C# 9 |
| positional | `point is (0, 0)` (uses `Deconstruct`) | C# 8 |
| list | `items is [var first, .., var last]` | C# 11 |

Why `is null` and not `== null`: `==` can be overloaded; `is null` always checks the reference.

**Tip:** a `switch` expression over an `enum` gives a compiler warning if a value is not handled
(unless you add `_`). For state machines, leaving out `_` on purpose makes the compiler find missing
cases when somebody adds a new enum value. With `TreatWarningsAsErrors`, that is a build break, which
is what you want.

---

## Collections and their complexity

| Collection | Lookup | Add | Remove | Notes |
|---|---|---|---|---|
| `T[]` | O(1) by index | n/a | n/a | fixed size |
| `List<T>` | O(1) index, O(n) `Contains` | O(1) amortized | O(n) | array that doubles |
| `LinkedList<T>` | O(n) | O(1) at a known node | O(1) at a known node | rarely the right choice |
| `Dictionary<K,V>` | O(1) average | O(1) average | O(1) | hash table, no order guarantee |
| `HashSet<T>` | O(1) average | O(1) | O(1) | set operations |
| `SortedDictionary<K,V>` | O(log n) | O(log n) | O(log n) | red-black tree, ordered |
| `SortedList<K,V>` | O(log n) | O(n) | O(n) | two arrays, less memory |
| `Queue<T>`, `Stack<T>` | n/a | O(1) | O(1) | |
| `PriorityQueue<T,P>` (.NET 6) | O(1) peek | O(log n) | O(log n) | min-heap |
| `ImmutableList<T>` | O(log n) | O(log n) | O(log n) | balanced tree, shares structure |
| `ImmutableArray<T>` | O(1) | O(n), copies | O(n) | fast reads, expensive changes |
| `ImmutableDictionary<K,V>` | O(log n) | O(log n) | O(log n) | slower reads than `Dictionary` |
| `FrozenDictionary<K,V>` (.NET 8) | O(1), faster than `Dictionary` | n/a | n/a | slow to create, read-only |
| `ConcurrentDictionary<K,V>` | O(1) | O(1) | O(1) | thread-safe, see chapter 04 |

How to choose:

- **Read-only data built once at startup** (a map of file extensions to parsers, language code
  tables): `FrozenDictionary` / `FrozenSet`. Creation does extra analysis of the keys to make reads
  faster. Do not build it per request.
- **Data you share between threads and replace as a whole** (a configuration snapshot): an
  immutable collection; readers never see a half-built state. Replace the reference atomically.
- **Data many threads change**: `ConcurrentDictionary` (chapter 04, Multithreading).
- **Order matters and you insert in the middle often**: think again about the data model before you
  reach for `LinkedList<T>`.

```csharp
private static readonly FrozenDictionary<string, string> _parsersByExtension =
	new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
	{
		[".docx"] = "word",
		[".xlsx"] = "excel",
		[".pptx"] = "slides",
	}.ToFrozenDictionary(StringComparer.OrdinalIgnoreCase);
```

**Common mistakes:**

- `list.Contains(x)` inside a loop over another list: O(n x m). Build a `HashSet` first.
- Exposing `List<T>` from a class: callers can change your internal state. Expose
  `IReadOnlyList<T>` or `IReadOnlyCollection<T>`.
- Assuming `Dictionary` keeps insertion order. It often seems to, until you remove an item.
- Forgetting capacity: `new List<T>(count)` and `new Dictionary<K,V>(count)` avoid regrowth when
  you know the size.

**Tip:** "Big-O" is not the whole story. A `List<T>` scan of 10 items is often faster than a
`HashSet` lookup because of memory locality. Say this in an interview, and then say you would
measure with BenchmarkDotNet before optimizing.

---

## At Smartcat: summary of the style rules that touch this chapter

| Topic | Rule | Source |
|---|---|---|
| Mongo models | `required` + `init`; no public `set` (D16, MINOR) | `backend-smartcat-codestyle`, `review-dotnet-style` |
| NRT | `#nullable enable` in new monolith files; project-wide in newer services | `backend-smartcat-codestyle` |
| Warnings | `TreatWarningsAsErrors=true`; nullable warnings fail the build | `Directory.Build.props` |
| Exceptions | no exception as success indicator (D8, MAJOR); use `TryX` or `Result<T>` | `review-dotnet-style` |
| Immutability across `await` | `sealed record` with `With*` methods (D6, MAJOR) | `review-dotnet-style` |
| LINQ | `Any(predicate)`, not `Where().Any()` / `Count() > 0` (D9, NIT) | `review-dotnet-style` |
| Lambdas | meaningful names (`pc => pc.Amount`), `_` only when unused | `backend-smartcat-codestyle` |
| Constants | no magic numbers; private constants `_camelCase` | `backend-smartcat-codestyle`, D1/D13 |
| Language | monolith builds with `LangVersion 14` on .NET 10 | `smartcat/Directory.Build.props` |

Naming of private methods differs by repo: the monolith style guide uses `camelCase` for private
methods, while `smartcat-ai-agents` follows its `.editorconfig` (PascalCase, rule D20). Follow the
repo you are in. Chapter 02 (Code style and naming the Smartcat way) covers this in detail.

---

## Interview corner

### As the interviewee

**1. What is the difference between a value type and a reference type?**
A strong answer covers:
- Value types hold data directly; assignment copies the data. Reference types hold a reference;
  assignment copies the reference.
- Examples of each, including that `string` is a reference type with value-like behavior.
- The consequence: changes to a copy of a struct are not visible to others.

**2. Do structs always live on the stack?**
A strong answer covers:
- No. A value lives where its container lives: a struct field in a class is on the heap; arrays of
  structs are on the heap; captured and async locals move to the heap; boxing puts it on the heap.
- The stack location is an implementation detail; the contract is copy semantics.
- Bonus: modern JIT escape analysis can even put some objects on the stack.

**3. What is boxing, and how do you avoid it?**
A strong answer covers:
- Value type converted to `object` or an interface: heap allocation plus copy.
- Hidden places: non-generic collections, interface variables, `string.Format`, struct keys without
  `IEquatable<T>`.
- Fixes: generics with constraints, `IEquatable<T>`, `record struct`, interpolated strings.

**4. Explain the `GetHashCode` contract.**
A strong answer covers:
- Equal objects must have equal hash codes; not the reverse.
- The hash must be stable while the object is a key; therefore keys should be immutable.
- What breaks if you violate it: lost items in `Dictionary` / `HashSet`.

**5. What does a `record` give you, and where does it surprise people?**
A strong answer covers:
- Value equality, `with`, `ToString`, deconstruction; `record struct` for value types.
- Equality and `with` are shallow: collection properties compare by reference.
- `EqualityContract`: different run-time types are not equal.

**6. What is the difference between `required` and a non-nullable type?**
A strong answer covers:
- `required` forces the caller to set the member at construction (compile-time check).
- Non-nullable is a flow-analysis promise that the value is not null.
- They combine: `required Guid? ProjectId` = must be set, may be null.

**7. Nullable reference types: what do they protect, and what do they not?**
A strong answer covers:
- Compile-time only; no run-time checks; deserializers and old callers can still pass null.
- `!` is an unchecked claim; attributes like `[NotNullWhen(true)]` teach the compiler.
- Validate at boundaries anyway.

**8. Explain covariance and contravariance with an example.**
A strong answer covers:
- `IEnumerable<out T>`: `IEnumerable<string>` as `IEnumerable<object>`.
- `Action<in T>`, `IComparer<in T>`: the opposite direction.
- Only interfaces and delegates, only reference types; `List<T>` is invariant; arrays are covariant
  and unsafe.

**9. Why does this loop print 333?** (the `for` closure example)
A strong answer covers:
- Closures capture variables, not values; one `i` for the whole `for` loop.
- `foreach` creates a new variable per iteration since C# 5.
- Fix with a local copy; mention allocation and lifetime of captured variables.

**10. What is deferred execution, and what is the risk?**
A strong answer covers:
- Query runs at enumeration, with the current values of captured variables.
- Multiple enumeration repeats the work, and may give different results.
- Materialize once (`ToList`) when you need to use the result several times.

**11. `IEnumerable` vs `IQueryable`?**
A strong answer covers:
- Delegates vs expression trees; in-memory vs translated by a provider.
- Methods that cannot be translated cause exceptions or in-memory evaluation.
- Returning `IEnumerable` from a repository can move filtering into memory.

**12. `throw` vs `throw ex`, and what are exception filters for?**
A strong answer covers:
- `throw` keeps the stack trace; `throw ex` resets it; wrap with an inner exception to add context.
- `when` filters run before unwinding; a false filter is as if the catch did not exist.
- Exceptions are for exceptional cases, not for flow control.

**13. When do you need a finalizer?**
A strong answer covers:
- Only when the class directly owns an unmanaged resource; prefer `SafeHandle`.
- Finalizable objects survive an extra GC and get promoted.
- Dispose pattern: `Dispose(bool)`, `GC.SuppressFinalize`.

**14. Describe the .NET GC.**
A strong answer covers:
- Generations 0/1/2, why generational works, LOH at 85,000 bytes, POH.
- Server vs workstation, background GC; DATAS in recent versions.
- Practical: avoid large buffers, use streaming and `ArrayPool`, leaks are forgotten references.

**15. What is `Span<T>` and why can it not be used across `await`?**
A strong answer covers:
- A `ref struct` view over memory; slicing without allocation.
- Stack-only: no fields in classes, no boxing, no lambdas, not across `await`.
- `Memory<T>` for async and storage.

### As the interviewer

**What to ask.** Start with one concrete code snippet and let the candidate explain the output. This
tests the model, not memory. Good openers: the `for` closure loop, the mutable `HashSet` key, the
`record` with a `List` property, `object == object` with two equal strings.

**Depth probes:**
- "You said structs live on the stack. Where does a struct field of a class live? And a local in an
  async method?"
- "You overrode `Equals`. What happens if you put this object in a `HashSet` and then change a
  property?"
- "This repository returns `IEnumerable<T>`. Where does the caller's `.Where` run?"
- "When would you choose `FrozenDictionary` over `Dictionary`? What does it cost?"
- "Why does an object with a finalizer cost more for the GC?"
- "`required` or a constructor? What are the tradeoffs for serialization and for callers?"

**Green flags:**
- Separates the language contract from the runtime implementation.
- Gives a real bug story: "we lost items in a dictionary because the key changed".
- Talks about tradeoffs (allocation vs readability, Big-O vs locality) and says "I would measure".
- Knows where the compiler helps (NRT, `required`, warnings for unhandled switch cases) and where it does not.

**Red flags:**
- Confident and wrong: "strings are value types", "the GC prevents all memory leaks".
- Uses `!` or `catch {}` to make problems go away.
- Cannot explain why `GetHashCode` must match `Equals`.
- Optimizes with `Span<T>` or structs everywhere without a reason.

**Scoring rubric:**

| Signal | Junior | Mid | Senior | Staff |
|---|---|---|---|---|
| Memory model | "structs on stack" | knows copy semantics | knows containers, captures, boxing | ties it to GC cost and design decisions |
| Equality | uses `==` | overrides `Equals` | full contract, immutable keys, records' shallow equality | sets team rules (records for DTOs, analyzers) |
| LINQ | uses it | knows deferred execution | multiple enumeration, `IQueryable` translation | designs repository APIs to prevent misuse |
| Errors and resources | try/catch | `using`, `throw;` | filters, Dispose pattern, async dispose | error strategy per boundary (HTTP, handlers, tasks) |
| Performance | none | knows `StringBuilder` | LOH, `ArrayPool`, `Span` with care | measures, sets budgets, knows when not to optimize |

---

## Exercises

1. **Find the bug.** A `HashSet<Customer>` loses customers after their email is updated. `Customer`
   overrides `Equals` and `GetHashCode` using `Email`. Explain and fix.
2. **Predict the output.** What does this print, and why?
   ```csharp
   var numbers = new List<int> { 1, 2, 3 };
   var query = numbers.Select(number => number * 10);
   numbers.Add(4);
   Console.WriteLine(string.Join(",", query));
   ```
3. **Write it.** Implement `readonly record struct LanguagePairKey` that compares source and target
   language codes case-insensitively. Make sure `GetHashCode` matches.
4. **Review it.** A colleague writes `public string Name { get; set; } = null!;` on a new Mongo model
   in the monolith. What do you suggest, and why?
5. **Explain it.** A service that converts uploaded documents shows high gen 2 GC counts and memory
   that never goes down. The code does `var bytes = await File.ReadAllBytesAsync(path)`. What is the
   likely cause and what would you change?
6. **Design it.** You have a map of 300 file extensions to processor names, loaded once at startup
   and read on every request from many threads. Which collection do you use, and why not the others?

<details>
<summary>Answer notes</summary>

1. The hash code depends on a mutable field. After the change, the object sits in the bucket for the
   old hash, so `Contains` and `Remove` look in the wrong bucket. Fix: use an immutable identity
   (`CustomerId`) for equality, or remove the item before the change and add it back after.
2. `10,20,30,40`. `Select` is deferred; the list is enumerated when `string.Join` runs, after `Add`.
3. A `record struct` generates equality that is case-sensitive for strings, so you must write
   `Equals(LanguagePairKey other)` and `GetHashCode()` yourself, using `StringComparison.OrdinalIgnoreCase`
   and `StringComparer.OrdinalIgnoreCase.GetHashCode(...)` with `HashCode.Combine`. The point of the
   exercise: the generated equality is not always the one you need.
4. Use `public required string Name { get; init; }` with `[BsonElement("name"), BsonRequired]`. The
   `null!` hides a missing value from the compiler; `required` makes every creator set it; `init`
   prevents later changes (rule D16). Also make sure the file has `#nullable enable`.
5. `ReadAllBytesAsync` creates one large `byte[]` per file; anything at 85,000 bytes or more goes to
   the LOH, which is collected only with gen 2 and not compacted by default. Stream the file in
   chunks with a pooled buffer (`ArrayPool<byte>`), and keep per-request memory bounded.
6. `FrozenDictionary<string, string>` with `StringComparer.OrdinalIgnoreCase`, in a `static readonly`
   field. It is read-only (thread-safe for reads) and optimized for lookups. `Dictionary` also works
   for concurrent reads with no writes, but is slower to read. `ConcurrentDictionary` adds
   synchronization cost you do not need. `ImmutableDictionary` has O(log n) reads.

</details>

---

## Summary

- A value lives where its container lives. "Structs on the stack" is a shortcut, not the rule.
- Boxing is a hidden allocation: watch interface variables, `object` parameters and struct keys.
- Equal objects must have equal hash codes, and keys must not change. Records help, but their
  equality is shallow.
- `required` means "must be set", NRT means "is not null". Smartcat Mongo models use
  `required` + `init`.
- NRT is compile-time only. Every `!` is a claim that deserves a review question.
- Closures capture variables, not values. `for` shares one variable; `foreach` does not.
- LINQ is deferred. Enumerate once; know whether your lambda becomes a delegate or an expression tree.
- `throw;` keeps the stack trace. Exceptions are not a way to return `false`.
- Dispose what you own. Finalizers only for raw unmanaged resources, and prefer `SafeHandle`.
- Big buffers go to the LOH. Stream, pool, and keep memory per request bounded.

Anki deck: anki/01-csharp-and-runtime.txt

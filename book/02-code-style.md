# 02. Code style and naming the Smartcat way

## Why this chapter matters

Style questions look easy in an interview. They are not. A good interviewer does not ask "what is
PascalCase". They show you ten lines of code and wait. They want to see whether you notice the
magic number, the exception used as a return value, the database model that is also the API
response. In real work, style is the cheapest review feedback to avoid and the most common review
feedback to receive. When the style is predictable, reviewers spend their attention on correctness.
This chapter gives you the rules, and the reason behind each rule, so you can defend them.

## What you will be able to do

- Name types, members, folders, indexes and enums in the way Smartcat reviewers expect.
- Write a MongoDB document model, a DTO and a config class in the house pattern, and explain why
  the three are different.
- Order members in a class and choose between a constructor, `required` + `init` and methods.
- Explain the tooling chain: `.editorconfig`, Roslyn analyzers, `TreatWarningsAsErrors`, nullable
  reference types.
- Recognize the D1–D28 review rules (magic numbers, dead code, `IConfiguration`, exceptions as
  success, async naming and more) in a diff and fix them.
- Tell a company convention from a general .NET rule, and say "it depends on the repo" with proof.

---

## 1. Where style rules come from (and which one wins)

There are three layers. Know them, because the layers do not always agree.

| Layer | Source | Enforced by |
|---|---|---|
| General .NET | .NET Runtime coding style, Framework Design Guidelines | habit, analyzers |
| Repository | `.editorconfig`, `Directory.Build.props` | IDE, `dotnet build`, `dotnet format` |
| Team review | review rules (D-, A-, T-series), reviewer memory | humans and AI review bots |

**The rule for conflicts:** the repository `.editorconfig` wins over a general guide, and the
prevailing pattern in the file you edit wins over your personal taste. Consistency inside one
codebase is worth more than any single rule being "right".

At Smartcat: the monolith (`smartcat/`), PTS (`project-tasks-service/`) and the newer AI service
(`smartcat-ai-agents/`) have **different** `.editorconfig` files. Two visible differences:

| Rule | Monolith / PTS | smartcat-ai-agents |
|---|---|---|
| Private method casing | `camelCase` (`processDocument()`) | `PascalCase` for all methods (rule D20) |
| `Async` suffix | almost never (PTS module: 0 of ~230 public `Task` methods) | yes (rule D15, ~670 methods) |
| Nullable | monolith: per file `#nullable enable`; PTS: global `Nullable=enable` | global `Nullable=enable` |
| Test names | `Should_x_when_y` | `Should_x_when_y` or `Method_Scenario_Expected` |

Tip: before your first commit in a new repo, open `.editorconfig` and `Directory.Build.props`.
It takes two minutes and saves a review round.

Interviewer view: "Your team and the .NET guidelines disagree on private method casing. What do you
do?" A strong answer: follow the repo, because tooling and reviewers enforce it; raise the
disagreement once, in a team discussion, not in every MR.

---

## 2. Naming conventions

### 2.1 The base table

| Element | Style | Example |
|---|---|---|
| Namespace | `Smartcat.{Solution}.{Project}.{Folder}` | `Smartcat.ImageService.Module.Services` |
| Class, public method, property | PascalCase | `ThingService`, `ProcessDocument` |
| **Private method** (monolith, PTS) | **camelCase** | `private void processDocument()` |
| Private field | `_camelCase` | `_documentService` |
| Private const, private static readonly | `_camelCase` | `_maxRetry`, `_retention` |
| Abbreviations | treat as a normal word | `LqaError`, `_lqaErrors` (not `LQAError`) |

**Why camelCase private methods?** In the monolith it makes visibility obvious at the call site.
When you read `validateScope(x)` you know it is private to this class. You do not need to scroll
or press "go to definition" to know that changing it cannot break another class. The general .NET
guidelines say PascalCase for all methods. Smartcat chose readability of visibility over the
general rule, and `.editorconfig` encodes it:

```ini
# smartcat/.editorconfig (excerpt)
dotnet_naming_rule.private_method_should_be_camel_case.symbols = private_method
dotnet_naming_rule.private_method_should_be_camel_case.style = camel_case
dotnet_naming_rule.private_constants_rule.style = begins_with_underscore_camelcase
```

**Why `_camelCase` for private constants?** The same idea: the underscore means "private state of
this class", and a private const is private state. Rule D13 flags `private const int MaxRetries`
and `private static readonly TimeSpan DefaultTimeout`.

Common mistake: assuming every repo follows the rule. In PTS you will find
`private const string CollectionName = "PendingScopeVolume";`
(`project-tasks-service/src/ProjectTasks.Module/DAL/PendingScopeVolumeRepository.cs`) next to
`private static readonly TimeSpan _retention`. The analyzer severity is `suggestion`, so old code
drifts. Do not copy the drift into new code, and do not "fix" it in an unrelated MR.

**Why abbreviations as normal words?** `LQAErrorsDTO` is hard to read and hard to split into
words. `LqaErrorsDto` reads as three words. It also makes the camelCase form obvious: `_lqaErrors`.

At Smartcat: old monolith code uses `AbbyyLS.SmartCAT.*` namespaces (the company history).
New projects use `Smartcat.{Solution}.{Project}.{Folder}`. Do not rename old namespaces. It breaks
serialized type names and creates a huge diff for no product value.

### 2.2 Folders and classes: plural folder, singular class

```
Services/
  ThingService.cs
Repositories/
  ThingRepository.cs
Mappers/
  ThingMapper.cs
```

Why: a folder is a collection ("the services"), a class is one thing ("a service"). This matches
how namespaces read: `Smartcat.ImageService.Module.Services.ThingService`.

### 2.3 Lambdas: `_` only when the parameter is not used

```csharp
// BAD: underscore for a parameter that is used
var total = projectCosts.Sum(_ => _.Amount);

// GOOD: a meaningful short name
var total = projectCosts.Sum(cost => cost.Amount);

// OK: underscore because the parameter is ignored
var all = items.Where(_ => true);
```

Why: in C# `_` reads as "discard". Using it as a real variable lies to the reader. Rule D21 adds:
in a lambda with a body of two or more lines that touches several members, use a name that
matches the type (`agent => ...`, `permission => ...`), not `x`. Single letters are fine for a
one-line `x => x.Id`.

### 2.4 Name says what the code does (D4, D22, D24)

| Name | Must mean |
|---|---|
| `XMapper` | pure `Map(Source) -> Target`, no side effects |
| `XBuilder` | mutable configuration, then `Build()` returns `X` |
| `XFactory` | creates `X` instances based on parameters |
| `TryAuthenticate` | verifies identity. If it returns a token, call it `TryResolveAccessTokenAsync` |

```csharp
// BAD (D4): a "Factory" that only maps, never creates anything new by choice
public sealed class InvoiceFactory
{
	public InvoiceDto Create(Invoice invoice) => new() { Id = invoice.Id, Total = invoice.Total };
}

// GOOD
public sealed class InvoiceMapper
{
	public InvoiceDto Map(Invoice invoice) => new() { Id = invoice.Id, Total = invoice.Total };
}
```

Why: a reader uses the name to guess the behavior. A "Mapper" with a database write inside is a
trap: someone calls it in a loop for a preview screen and writes data by accident.

D24 (AI tools): output records from several tools that all have `Id` and `Name` confuse the
consumer (here, an LLM). Prefix with the domain: `CustomTemplateId`, `CustomTemplateName`.

### 2.5 One term per concept (D17, D19)

```csharp
// BAD (D17): two names for the same concept in one file
Task<Agent> GetByTag(string tag);
Task Delete(string code);   // "code" is the same value as "tag"

// GOOD
Task<Agent> GetByTag(string tag);
Task DeleteByTag(string tag);
```

D19 is the same rule for a known Smartcat drift: **Account vs Workspace**. Historically the
monolith calls a workspace an "account" (`AccountId`). Newer APIs say `Workspace`. Inside new
code, pick the term the surrounding new code uses. Do not mix `accountId` and `workspaceId`
parameters when there is only one real boundary. Mixed terms make readers ask "are these two
different things?", and sometimes they are, so the question is expensive.

Example from the monolith: `ApplyProjectTtsModelTask` has `AccountId` with the comment
"Account ID (workspace)" (`smartcat/Features/Cat/Core.Contract/DocumentProcessing/TaskEntities/ApplyProjectTtsModelTask.cs`).
The comment exists because the term is ambiguous.

---

## 3. Enumerations

```csharp
// "Document status is Draft" reads as a sentence
public enum DocumentStatus
{
	Draft,
	Processing,
	Completed,
	Failed
}

// Flags: plural name or Flags suffix, explicit None = 0, combinations by bitwise OR
[Flags]
public enum DocumentOptions
{
	None = 0,
	ReadOnly = 1,
	Hidden = 2,
	ReadOnlyAndHidden = ReadOnly | Hidden
}
```

Rules and the why:

- **Suffix `Status`, `Type`, `Mode`, `State`, `Style`, never `Enum`.** `DocumentStatusEnum` adds a
  word that the type system already tells you.
- **"Name + is + value" forms a sentence.** If it does not, the name is probably wrong.
- **Order: alphabetical or semantic** (the lifecycle order above). Never random.
- **Flags: combine with `|`, not literals.** `ReadOnlyAndHidden = 3` breaks silently when someone
  renumbers `Hidden`.
- **Status as a value, not as a class hierarchy (A8).** `RunningStatus`, `ActiveStatus` classes with
  no fields are an enum in disguise. Put behavior in a service and compare values.

Common mistake: storing enums as numbers in MongoDB. See section 4.2.

---

## 4. MongoDB models

### 4.1 The standard model pattern

```csharp
public sealed class MyDocument
{
	[BsonId, BsonRequired]
	public required ObjectId Id { get; init; }

	[BsonElement("accountId"), BsonRequired]
	public required Guid AccountId { get; init; }

	[BsonElement("name"), BsonRequired]
	public required string Name { get; init; }

	[BsonElement("status"), BsonIgnoreIfDefault, BsonRepresentation(BsonType.String)]
	public DocumentStatus Status { get; init; }

	[BsonElement("createdAt"), BsonRequired]
	public required DateTime CreatedAt { get; init; }
}
```

| Element | Why |
|---|---|
| `sealed` | a stored model is data, not a base class. Inheritance in BSON needs discriminators |
| `required` | the compiler forces every creator to set the field. No half-built documents |
| `init` | the object is immutable after creation. Mutation goes through explicit update methods |
| `[BsonElement("camelCase")]` | the DB name is fixed and independent from the C# name |
| `[BsonRequired]` | deserialization fails loudly if a mandatory field is missing |
| `[BsonIgnoreIfDefault]` / `[BsonIgnoreIfNull]` | optional fields do not waste space in every document |

**Why an explicit `[BsonElement]` name on every field?** Because the C# name and the stored name
have different lifetimes. You can rename a property in one click. You cannot rename a field in a
collection with 200 million documents in one click. With an explicit name, a rename is a safe
refactoring. Real example: in `ApplyProjectTtsModelTask` the property is `UserId`, but the stored
name stays `initiatedByAccountUserId`. Someone renamed the property and kept the data.

**Why camelCase in the database?** Consistency with JSON and with the rest of the stored data,
and because migrations and indexes refer to the stored name. A known review BLOCKER: a migration
builds an index on `"AccountId"` (PascalCase) while the model stores `"accountId"`. The index is
created, it is valid, and no query ever uses it.

Rule D16 (MINOR): a Mongo-mapped class with `{ get; set; }` properties. Fix: `required` + `init`,
and use factory or update methods for changes.

Older pattern you will see (and should not rewrite without reason): constructor + `private set`
+ a private parameterless constructor for the serializer:

```csharp
// project-tasks-service/src/ProjectTasks.Module/DAL/Schema/PendingScopeVolume.cs (shortened)
public sealed class PendingScopeVolume
{
	// ReSharper disable once UnusedMember.Local
	private PendingScopeVolume()
	{
	}

	public PendingScopeVolume(string documentId, Guid stageId /* ... */)
	{
		DocumentId = documentId;
		StageId = stageId;
	}

	[BsonElement("stageId"), BsonRequired]
	public Guid StageId { get; private set; }
}
```

Both patterns protect the invariant "nobody mutates a loaded document by accident". The new one
does it with less code.

### 4.2 Enum and Guid representation

```csharp
[BsonElement("status"), BsonRequired, BsonRepresentation(BsonType.String)]
public required DocumentStatus Status { get; init; }

[BsonElement("externalId"), BsonRequired]
public required Guid ExternalId { get; init; }
```

**Why store enums as strings?** Three reasons:

1. **Safe reordering.** If the enum is stored as an int and someone inserts a new value in the
   middle, every stored document silently changes meaning. `Failed` becomes `Completed`.
2. **Readable data.** On-call engineers read raw documents in production. `"status": "Failed"`
   needs no lookup table.
3. **Safe queries from other tools** (analytics, ad-hoc scripts) that do not know the C# enum.

The cost is a few bytes per document. That is a good trade.

Real example: `smartcat/Features/Cat/Core.Contract/Projects/DocumentTargetStatusSnapshot.cs`
stores `[BsonElement("status"), BsonRequired, BsonRepresentation(BsonType.String)]`.

**Guids:** keep the representation the collection already uses. Mixing representations in one
collection (legacy binary subtype 3 vs standard subtype 4) makes `Eq` filters miss documents.
Tip: if a Guid filter "finds nothing" but you see the document in a tool, check the binary
subtype first.

### 4.3 Separate models for DB, API input and API output

```csharp
// BAD: one class for everything
public class Document { /* stored, returned, accepted */ }

// GOOD: three classes with three reasons to change
public sealed class DocumentEntity { /* DB storage */ }
public sealed class CreateDocumentRequest { /* API input */ }
public sealed class DocumentResponse { /* API output */ }
```

Why:

- **Security.** If the API input type is the DB type, a client can set fields it must not set
  (`IsAdmin`, `AccountId`). This is "mass assignment" (OWASP; see chapter 13 (Secure .NET code)).
- **Change independence.** Adding an internal field must not change the public contract, and a
  contract change must not need a data migration.
- **Different shapes.** The DB wants `required` + `init` + BSON attributes. The DTO wants
  serializer friendliness.

### 4.4 Contracts and DTOs

```csharp
// No constructors, public setters, no attributes
public sealed class CreateDocumentRequest
{
	public string Name { get; set; } = string.Empty;
	public Guid AccountId { get; set; }
}
```

Why the "opposite" of the Mongo rules? A DTO crosses a process boundary. Serializers, model
binders and generated API clients all work best with a parameterless constructor and setters. A
DTO has no invariants to protect; validation happens at the boundary (model validation, a
validator) and in the domain. Default `string.Empty` avoids `null` surprises when a client omits
the field.

Exception: in published API contracts (the `*.Contracts` / `*.ApiClient` NuGet packages) you will
see `[DataMember(Name = "camelCase")]`. When it is there, the name must be camelCase and match the
JSON field. A wrong casing there is a contract break (a review warning in the backend checklist).

### 4.5 Config classes

```csharp
internal sealed class MyServiceConfig
{
	public required string ConnectionString { get; init; }
	public required int MaxRetries { get; init; }
	public int Timeout { get; init; } = 30;
}
```

Why: `required` makes a missing mandatory key fail at startup (fail fast), not at 3 AM on the first
request that needs it. `init` makes config immutable after binding. A default value documents the
normal value in code. `internal` because only this module reads it.

Note: binding through `IConfiguration.Bind`/`Get<T>` may set `required` members through
reflection and not throw on its own. Validate at startup (`ValidateOnStart()`, data annotations or
a check in the module) when a missing value must stop the service. The real PTS code reads
`config.Value.BatchSize!.Value` — a nullable value with a `!` — so in that code a missing key
fails at construction time.

See section 9 for `IOptions<T>` and chapter 05 (ASP.NET Core) for the full config pipeline.

---

## 5. Index naming

| Type | Prefix | Example |
|---|---|---|
| Unique | `UDX_` | `UDX_AccountId_Name` |
| Non-unique | `IDX_` | `IDX_State_UpTime` |
| TTL (convention seen in code) | `IDX_..._TTL` | `IDX_UpdatedAt_TTL` |

```csharp
// project-tasks-service/src/ProjectTasks.Module/DAL/PendingScopeVolumeRepository.cs
_collection.SafeCreateIndex(
	Builders<PendingScopeVolume>.IndexKeys.Ascending(x => x.UpdatedAt),
	new CreateIndexOptions<PendingScopeVolume>
	{
		Name = "IDX_UpdatedAt_TTL",
		ExpireAfter = _retention,
	});
```

**Why a prefix?** You read index names in `explain()` output, in slow query logs and in
`listIndexes`. `UDX_` tells you instantly that the index enforces a business rule. Dropping it is
not a performance decision. It is a data-integrity decision.

**Why list the fields in the name?** The order of fields in a compound index matters (equality
fields first, then sort, then range). A name like `IDX_State_UpTime` lets a reviewer check the
order without opening the definition.

**Keep existing `IX_` names.** An index is identified by its name. Renaming means drop + create.
On a big collection that is a long index build, extra load on the primary and a window where the
queries run without the index. A rename gives zero value for that risk.

Who creates the index (repository warmup with `SafeCreateIndex` vs a migration with
`EnsureIndexAsync`) is a separate topic: see chapter 09 (MongoDB models, indexes and safe
migrations) and rules A24/A25 in chapter 12 (Code review).

---

## 6. Member ordering

```csharp
public class MyService
{
	// 1. public: const -> fields -> constructor/methods -> properties
	public const string Version = "1.0";
	public MyService(ILogger<MyService> logger, IDocumentService documentService)
	{
		_logger = logger;
		_documentService = documentService;
	}

	public void Process() => processInternal();

	public string Name { get; } = "my-service";

	// 2. internal: const -> fields -> methods -> properties
	internal void InternalMethod() { }

	// 3. protected: const -> fields -> methods -> properties
	protected virtual void OnProcess() { }

	// 4. private, first block: methods -> properties
	private void processInternal() { }

	private string InternalName => Name.ToUpperInvariant();

	// 5. private, second block: const -> fields (at the very end)
	private const int _maxRetries = 3;
	private readonly ILogger<MyService> _logger;
	private readonly IDocumentService _documentService;
}
```

**Why public first and private fields last?** A reader opens a class to learn what it offers.
The public surface is the contract. Private fields are implementation detail, so they go to the
bottom. This is a Smartcat choice; many .NET codebases put fields at the top. Again: match the
file.

Note on the source: the codestyle skill example shows `public const string _version`. The
analyzer rule with the underscore applies to **private** constants. For public constants use
PascalCase, as in .NET in general (likely the intended rule; the example looks like a typo).

Common mistake: adding a new private field at the top "because the IDE put it there". The backend
reviewer checklist has a `member-ordering` item, so this comes back as a warning.

---

## 7. Constructors vs `required` + `init`

```csharp
// Immutable: everything through the constructor
public sealed class Money
{
	public Money(decimal amount, string currency)
	{
		ArgumentOutOfRangeException.ThrowIfNegative(amount);
		Amount = amount;
		Currency = currency;
	}

	public decimal Amount { get; }
	public string Currency { get; }
}

// Mutable: the essential identity through the constructor, the rest through methods
public sealed class DocumentDraft
{
	public DocumentDraft(Guid id)
	{
		Id = id;
	}

	public Guid Id { get; }
	public string? Name { get; private set; }

	public void Rename(string name)
	{
		ArgumentException.ThrowIfNullOrWhiteSpace(name);
		Name = name;
	}
}
```

How to choose:

| Use | When |
|---|---|
| Constructor | the type has invariants to check (validation, derived values) |
| `required` + `init` | data carriers (Mongo models, configs, events) with many fields and no logic |
| Methods with `private set` | the object changes over time; each change has a name and a check |

**Why not public setters on domain objects?** A setter has no name for the business action. `Name
= x` does not say "rename"; it cannot check rules; it can be called from anywhere. A method
`Rename(x)` is searchable, testable and can protect an invariant (see A31 in chapter 12).

Interview point: `required` (C# 11) is checked at compile time for object initializers. It is not
a runtime guarantee: reflection-based deserializers can still skip it (System.Text.Json honors
`required` since .NET 7; the Mongo driver does not, which is why you also need `[BsonRequired]`).

---

## 8. Nullable reference types

```csharp
#nullable enable

public sealed class ProfileService
{
	private readonly ILogger<ProfileService> _logger;   // never null
	private readonly IProfileCache? _cache;              // optional dependency

	public ProfileService(ILogger<ProfileService> logger, IProfileCache? cache = null)
	{
		_logger = logger;
		_cache = cache;
	}

	public string Normalize(string input) => input.Trim();   // non-null in and out

	public Profile? TryFind(Guid id) => _cache?.Get(id);    // null means "not found"
}
```

At Smartcat:

- **Monolith**: nullable is **not** enabled globally (it is a large old codebase). Add
  `#nullable enable` at the top of every **new** file. When you edit an old file, do not enable it
  for the whole file in the same MR; that turns a 5-line change into 200 warnings. If you need it
  for a block, use `#nullable enable` ... `#nullable restore` around your code.
- **PTS, smartcat-ai-agents**: `Nullable=enable` and `TreatWarningsAsErrors=true` in
  `Directory.Build.props`. If nullable code compiles, the annotations are consistent.

**Why it matters:** `NullReferenceException` is still the most common production exception in
.NET. Nullable annotations move that class of bug from runtime to compile time. They also document
intent: `Profile?` says "not found is normal", `Profile` says "not found is a bug".

Common mistake: `!` (null-forgiving) everywhere to silence warnings. Each `!` is a claim "I know
better than the compiler". Use it only when you can say why (for example after a validated
config bind), not to finish faster.

---

## 9. General .NET style that reviewers check

### 9.1 The tooling chain

```xml
<!-- Directory.Build.props (PTS, shortened) -->
<PropertyGroup>
	<Nullable>enable</Nullable>
	<TreatWarningsAsErrors>true</TreatWarningsAsErrors>
	<LangVersion>14</LangVersion>
</PropertyGroup>
```

| Tool | What it does | Why it matters |
|---|---|---|
| `.editorconfig` | indentation (tabs at Smartcat), naming rules, `var` preferences, line length | one style for IDE, CLI and CI |
| Roslyn analyzers | code quality rules (CAxxxx), style rules (IDExxxx) | finds bugs a human misses |
| `TreatWarningsAsErrors` | a warning fails the build | warnings never pile up |
| `dotnet format` | applies `.editorconfig` | fixes whitespace without arguments |

**Why `TreatWarningsAsErrors`?** In a codebase where warnings are allowed, there are soon 3000
warnings and nobody reads them. The one that says "possible null dereference" in your new code is
invisible. With warnings as errors, the count stays at zero, so every new warning is visible.

D12 (NIT): new `*.cs` files indented with spaces. Smartcat C# uses tabs per `.editorconfig`. Fix
with `dotnet format whitespace --include <file>`. Max line width in the monolith is 120
(`resharper_csharp_max_line_length = 120`).

### 9.2 `IOptions<T>` over raw `IConfiguration` (D5)

```csharp
// BAD (D5): business class reads raw configuration
public sealed class ExportService(IConfiguration configuration)
{
	public int BatchSize => configuration.GetSection("Export").Get<ExportOptions>()!.BatchSize;
}

// GOOD: typed options bound once in the module
public sealed class ExportOptions
{
	public required int BatchSize { get; init; }
}

// Module.cs
services.AddOptions<ExportOptions>()
	.BindConfiguration("Export")
	.ValidateDataAnnotations()
	.ValidateOnStart();

public sealed class ExportService(IOptions<ExportOptions> options)
{
	private readonly int _batchSize = options.Value.BatchSize;
}
```

Why:

- **Testability.** `Options.Create(new ExportOptions { BatchSize = 10 })` in a test, versus building
  a fake configuration tree.
- **One place for keys.** The section name lives in the module, not in ten classes.
- **Validation at startup**, not at first use.
- **Explicit dependency.** The constructor says "I need export settings", not "I can read anything".

`IOptions<T>` (singleton, read once), `IOptionsSnapshot<T>` (scoped, re-read per request),
`IOptionsMonitor<T>` (singleton with change notification). Interviewers love this question; see
chapter 05.

At Smartcat: PTS registers settings with `services.AddConfigOptions<T>()` (a Smartcat AppPlatform
helper, `project-tasks-service/src/Common/SettingsModule.cs`) and task processors take
`IOptions<DeadlineNotificationProcessorConfig>`. `IConfiguration` itself appears only in
`Module.Load(IServiceCollection, IConfiguration)`, which is exactly where D5 allows it. For secrets
and crypto config the same issue is a security finding (S17, chapter 13).

### 9.3 The `Async` suffix (D15)

```csharp
public Task<Agent?> FindAgentAsync(Guid id, CancellationToken ct);  // smartcat-ai-agents style
public Task<Scope> Get(Guid id, CancellationToken ct = default);    // PTS / monolith style
```

The .NET guideline is "methods that return awaitables end with `Async`". D15 enforces it in
smartcat-ai-agents and also flags the reverse: an `Async` suffix on a method that does not return
a task. The monolith and PTS mostly do not use the suffix (the PTS module has zero public `Task`
methods with it). Follow the repo. In an interview, state the guideline and add "I follow the
codebase".

Why the guideline exists: it warns the caller to `await`. Without the suffix, `repo.Delete(id);`
without `await` looks fine in review and becomes fire-and-forget. With nullable and
`TreatWarningsAsErrors`, CS4014 catches the obvious case inside async methods; it does not catch
`_ = repo.Delete(id)` or a non-async caller.

### 9.4 Exceptions are not a success indicator (D8, MAJOR)

```csharp
// BAD: exception as control flow
public bool IsValidLanguage(string code)
{
	try
	{
		_languageService.Check(code);
		return true;
	}
	catch
	{
		return false;
	}
}

// GOOD: a Try pattern
public bool TryGetLanguage(string code, [NotNullWhen(true)] out Language? language)
{
	language = _languages.GetValueOrDefault(code);
	return language is not null;
}
```

Why MAJOR and not MINOR:

- **Cost.** Throwing captures a stack trace. In a loop over 50 000 segments, this is visible in CPU
  profiles.
- **Bare `catch` hides real failures.** `OutOfMemoryException`, a timeout, a bug in `Check` all
  become "invalid language".
- **Monitoring noise.** Sentry and logs fill with expected exceptions, so real ones get lost.

Use exceptions for exceptional situations (broken invariant, infrastructure failure). Use
`bool TryX(out T)`, `T?` or a `Result<T>` type for expected outcomes like "not found" or "invalid
input".

### 9.5 Mutable objects across `await` (D6, MAJOR)

```csharp
// BAD: shared mutable list changed across awaits
private readonly List<string> _errors = new();

public async Task Validate(IEnumerable<Item> items)
{
	foreach (var item in items)
	{
		if (!await _checker.IsValid(item))
			_errors.Add(item.Id);   // two concurrent calls corrupt the list
	}
}

// GOOD: local state, immutable result
public async Task<IReadOnlyList<string>> Validate(IEnumerable<Item> items)
{
	var errors = new List<string>();
	foreach (var item in items)
	{
		if (!await _checker.IsValid(item))
			errors.Add(item.Id);
	}
	return errors;
}
```

Why: after `await`, the code may continue on another thread, and other requests may run in
between. A mutable object that is shared (a field in a singleton, an object passed to two tasks)
becomes a race. Prefer `sealed record` with `with` expressions or local state. See chapter 03
(Async and await) and chapter 04 (Multithreading).

### 9.6 Smaller readability rules

**No magic numbers (D1, MINOR).**

```csharp
// BAD
if (items.Count > 3) { /* ... */ }
await Task.Delay(5000);

// GOOD
private const int _maxDescriptionItems = 3;
private static readonly TimeSpan _retryDelay = TimeSpan.FromSeconds(5);
```

Why: the name explains the meaning; the constant is one place to change. Exempt: `0`, `1`, `-1`,
size hints, test data. A38 is the same rule for lifecycle durations (lock TTL, cache TTL, lease):
use a named constant or an options class with a short doc comment saying why that value.

Tip: `TimeSpan` constants beat `int` milliseconds. `_retryDelayMs = 5000` still makes the reader do
arithmetic; `TimeSpan.FromSeconds(5)` does not.

**Nesting deeper than two levels (D7, MINOR).** Use guard clauses:

```csharp
// GOOD
public void Publish(Document? document)
{
	if (document is null)
		return;
	if (!document.IsReady)
		return;

	_publisher.Publish(document);
}
```

**LINQ (D9, NIT).** `Where(p).Any()` -> `Any(p)`; `Where(p).Count() > 0` -> `Any(p)`; the same
multi-condition predicate in two places -> an extension method in the shared utilities folder.

**Mongo filter builders (the second D23, NIT).** `Builders<T>.Filter.And(a, b)` -> `a & b`.
Shorter, same result.

---

## 10. Comments policy: code is self-descriptive

The Smartcat position is simple: **production logic has no inline comments unless one is truly
needed**. Express intent with names, small methods and types.

```csharp
// BAD: the comment repeats the code
// check if the scope is completed
if (scope.Status == ScopeStatus.Completed) { /* ... */ }

// GOOD: the name carries the meaning
if (scope.IsCompleted) { /* ... */ }
```

When a comment is allowed:

- **A non-obvious invariant or a workaround** for an external bug: say *why*, not *what*.
- **Member-level doc comments (`///`)** on public or non-obvious members, **1–2 lines**.
- **TTL and lease fields** (A39): a short block saying who writes it, who cleans up, the worst
  staleness window, and what happens on a crash. This is the one place where a longer comment is
  expected, because the contract is invisible in code.

Formatting rules:

- **No dot at the end of a one-line comment.** `// Keeps the old name for compatibility`.
- **English only** in code, comments, config file names and config keys (D10). Values may be in any
  language.
- **Max line width** of the repo (120 in the monolith).

Review rules about comments:

| Rule | Pattern | Severity |
|---|---|---|
| D3 | `TODO`/`FIXME`/`HACK` for a feature that already shipped; block comments around removed code | NIT |
| D26 | "will be improved later", "placeholder for" without a ticket | NIT |
| D18 | `TODO` or `placeholder` inside `Directory.Packages.props` / `*.csproj` | NIT |
| backend checklist | TODO left in the diff | warning |

Fix for D26: link the ticket (`// TODO(DEV-12345): remove after the v2 rollout`) or delete it.
A promise without a ticket is never kept.

Why so strict? Comments go stale. The compiler checks code; nobody checks comments. A wrong
comment is worse than no comment, because the reader trusts it. Longer reasoning belongs in the MR
description, where it is tied to the change and its date.

---

## 11. Local functions

Use them carefully: only when they **significantly** simplify the code compared to a private
method. "The method is only used here" is not a sufficient reason.

```csharp
// Reasonable: iterator with eager argument validation
public static IEnumerable<T> Batch<T>(IEnumerable<T> source, int size)
{
	ArgumentNullException.ThrowIfNull(source);
	ArgumentOutOfRangeException.ThrowIfLessThan(size, 1);
	return iterate();

	IEnumerable<T> iterate()
	{
		// ... yield return batches
		yield break;
	}
}
```

Why the caution: a local function hides inside a long method, captures variables silently (which
can allocate a closure), and cannot be tested alone. A private method has a visible signature and
a place in the member order. Good cases: iterator or async methods that must validate arguments
eagerly, and small recursive helpers. Mark them `static` when they do not need captures.

---

## 12. MR hygiene rules in the D-series

Some D-rules are not about code lines. They are about the change as a whole.

| Rule | Pattern | Severity | Why |
|---|---|---|---|
| D2 | dead code from a merge: unreferenced new methods, `*Old.cs`, `*V2.cs`, "legacy from branch" | MAJOR | dead code looks alive; the next developer maintains it |
| D11 | pre-release NuGet (`-alpha`, `-beta`, `-rc`, `-preview`) pinned for production | BLOCKER | unstable API and no support promise. Exception: `Microsoft.Agents.AI`, pre-1.0 by design (MINOR) |
| D25 | one MR mixes several task IDs and module domains | MINOR | cannot review, revert or release one part |
| D27 | title says "bump X to Y" but the diff does not contain it | BLOCKER | the MR description is a claim; ship reality, not intent |
| D28 | branch far behind target; the diff shows fake "removals" | MAJOR | reviewers waste time; rebase before review |

D28 check: `git rev-list --count <branch>..<target>` (commits on target that the branch does not
have). More than about 10 -> rebase first.

These connect directly to chapter 12 (Code review): a good MR is small, honest and current.

---

## At Smartcat (summary of house conventions)

- `.editorconfig` per repo is the source of truth; tabs; 120 columns in the monolith.
- Monolith and PTS: private methods `camelCase`; smartcat-ai-agents: PascalCase everywhere.
- Private fields, private constants and private static readonly: `_camelCase`.
- Mongo models: `sealed`, `required` + `init`, `[BsonElement("camelCase")]`, `[BsonRequired]`,
  enums as strings. Older code uses constructor + `private set`; both are fine to keep.
- Separate DB entity, API request and API response types.
- New indexes: `IDX_` / `UDX_` with fields in the name. Never rename an existing `IX_` index.
- Members: public, internal, protected, private methods/properties, then private const and fields.
- Monolith: `#nullable enable` in every new file. Services: global nullable + warnings as errors.
- Tests: `Should_x_when_y`, AAA with blank lines (chapter 10 (Unit and integration testing)).
- No inline comments in production logic unless needed; `///` 1–2 lines; no trailing dots.

---

## Interview corner

### As the interviewee

**1. Why would a team use camelCase for private methods when .NET guidelines say PascalCase?**
A strong answer covers:
- Visibility is visible at the call site; you know a change is local.
- The repo `.editorconfig` encodes it, so tooling enforces it, not memory.
- Consistency within a codebase beats a general guideline. You follow it and discuss changes once.

**2. Why `[BsonElement("name")]` on every field if the driver can map by convention?**
- Decouples the C# name from the stored name; renames become safe.
- Prevents PascalCase/camelCase mismatches between model, migration and index.
- Makes the stored schema explicit in code review.

**3. Why store an enum as a string in MongoDB?**
- Int storage breaks silently when someone reorders or inserts a value.
- Raw documents are readable during incidents.
- External tools can query without knowing the enum.
- Costs a few bytes; worth it.

**4. Why not use one class for the DB entity and the API response?**
- Mass-assignment risk on input.
- Internal changes leak into the public contract and the other way.
- Different technical needs (BSON attributes vs serializer-friendly DTO).

**5. `required` + `init` vs a constructor: when each?**
- Constructor: invariants, validation, derived values.
- `required` + `init`: data carriers with many fields; compile-time completeness.
- Mention that `required` is not enforced by every deserializer; add `[BsonRequired]` or
  startup validation.

**6. What does `TreatWarningsAsErrors` give you, and what does it cost?**
- Warning count stays zero, so new warnings are visible.
- Cost: upgrades (new analyzers, new SDK) can break the build; you need a policy for suppressions
  (`#pragma` with a reason, or `.editorconfig` severity).

**7. `IOptions<T>` vs `IOptionsSnapshot<T>` vs `IOptionsMonitor<T>`?**
- Singleton read-once / scoped per request / singleton with change callbacks.
- Snapshot cannot be injected into a singleton.
- Why typed options at all: testability, validation, one place for keys.

**8. When is it acceptable to catch an exception and return false?**
- At a boundary with a third-party API that only signals by exceptions, catching a **specific**
  exception type, with logging.
- Never a bare `catch`; never inside your own domain where a Try method is possible.

**9. Why are magic numbers a problem if the code works?**
- Meaning is lost; change needs search and guess; the same value drifts in two places.
- Durations: prefer `TimeSpan` constants or options with the reason in a doc comment.

**10. What is your view on comments?**
- Code says what; names say why at small scale; comments only for non-obvious why.
- Comments go stale and are not compiled.
- `///` on public API, short. Longer reasoning in the MR description.

**11. Why must you not rename an existing index?**
- Index identity is its name; rename = drop + create.
- Long build on large collections, primary load, a window without the index.

**12. How do you enable nullable in a large legacy codebase?**
- Per file for new code (`#nullable enable`); never flip a whole old file inside a feature MR.
- Then module by module, as separate MRs, with warnings as errors once a module is clean.

**13. What is wrong with an `Async` suffix debate in review?**
- It is a repo convention question; the answer is in the codebase. Point to the rule, not to taste.

### As the interviewer

**What to ask.** Give a 30–40 line class that mixes: a Mongo model with `{ get; set; }` used as an
API response, an int-stored enum, a `try/catch return false`, a magic `5000`, a raw
`IConfiguration`, an `_` lambda used as a value, and a comment that repeats the code. Ask: "Review
this as if it were an MR. Order your findings by importance."

**Depth probes.**
- "Which of these would you block the MR for, and which would you only mention?" (calibration)
- "The team insists on int enums for space. Convince them, or accept it with what safeguard?"
- "The model is shared by the API and the DB today. How do you split it without downtime?"
- "Your `.editorconfig` says camelCase private methods but analyzers are only `suggestion`. Would
  you raise the severity? What happens to the 4000 old violations?"

**Green flags.**
- Orders findings by risk: exception-as-success and the shared model first, naming last.
- Explains every rule with a failure scenario, not "because the guide says".
- Knows that conventions are repo-specific and checks the repo before arguing.
- Proposes a concrete fix for each finding, including a migration plan for stored data.

**Red flags.**
- Spends five minutes on spacing and misses the shared DB/API model.
- "I would rename the index to follow the new convention" (no cost awareness).
- Calls style "subjective" and refuses to follow team rules, or the opposite: cannot explain any
  rule beyond "it is the standard".

**Scoring rubric.**

| Level | Signals |
|---|---|
| Junior | finds naming and magic numbers; cannot explain why; no severity order |
| Senior | finds all issues; explains failure modes; orders by severity; proposes fixes |
| Staff | adds rollout thinking (enum as string on existing data, model split without downtime, analyzer severity rollout); separates repo convention from general truth; knows when *not* to change old code |

---

## Exercises

1. **Fix the model.** Rewrite this class in the Smartcat pattern and list each change with its
   reason.

   ```csharp
   public class Invoice
   {
   	public ObjectId Id { get; set; }
   	public Guid AccountId { get; set; }
   	public InvoiceState State { get; set; }   // stored as int today
   	public string Number { get; set; }
   	public DateTime? PaidAt { get; set; }
   }
   ```

2. **Find the review comments.** List findings with severity (BLOCKER/MAJOR/MINOR/NIT):

   ```csharp
   public class LimitChecker
   {
   	private readonly IConfiguration _cfg;
   	private const int MaxItems = 50;

   	public LimitChecker(IConfiguration cfg) { _cfg = cfg; }

   	public bool CanAdd(Workspace ws, int accountItems)
   	{
   		try
   		{
   			Check(ws, accountItems);
   			return true;
   		}
   		catch { return false; }
   	}

   	// checks the limit.
   	private void Check(Workspace ws, int items)
   	{
   		if (items > int.Parse(_cfg["Limits:Max"]!) || items > MaxItems) throw new LimitException();
   	}
   }
   ```

3. **Index naming.** You add a unique index on `(accountId, slug)` and a non-unique index on
   `(state, upTime)` to an existing collection that already has `IX_State`. Name the new indexes and
   say what you do with `IX_State`.

4. **Comment cleanup.** Rewrite these comments or remove them:
   - `// increment the counter.`
   - `// will be improved later`
   - `// we skip archived scopes because the progress service ignores them and would loop forever`

5. **Repo detective.** Open `.editorconfig` and `Directory.Build.props` of two repos you work with.
   Write down five differences and the rule you will follow in each repo.

<details>
<summary>Answer notes</summary>

**1.** `sealed`; `[BsonId, BsonRequired] public required ObjectId Id { get; init; }`;
`[BsonElement("accountId"), BsonRequired] required Guid AccountId`;
`[BsonElement("state"), BsonRequired, BsonRepresentation(BsonType.String)] required InvoiceState State`;
`[BsonElement("number"), BsonRequired] required string Number`;
`[BsonElement("paidAt"), BsonIgnoreIfNull] DateTime? PaidAt { get; init; }`. The enum change is a
**data migration**, not a code change: stored values are ints. Plan: support reading both forms
(a custom serializer or a migration that rewrites the field), migrate, then switch. Check the
current stored element names before adding `[BsonElement]`: if the data has `"AccountId"`, keep
that name or migrate. Also: `PaidAt` changes belong in a named method, not a setter. Mark the
file `#nullable enable` in the monolith.

**2.** MAJOR D8: exception as success with bare `catch`. MINOR D5: raw `IConfiguration` in a
business class, parsed on every call (also a runtime `FormatException` risk). MINOR D17/D19:
`ws` is a `Workspace` but the parameter is `accountItems`. NIT D13: `MaxItems` should be
`_maxItems`. NIT: private method `Check` should be `check` in the monolith/PTS (PascalCase in
smartcat-ai-agents). NIT: the comment repeats the name and ends with a dot; delete it.
Fix: `LimitOptions` via `IOptions<LimitOptions>`, `bool CanAdd(...) => items <= _maxItems`.
Also ask: why are there two limits (config and const)? That is a design question, likely a bug.

**3.** `UDX_AccountId_Slug` (unique, tenant-scoped — see A27 in chapter 12) and
`IDX_State_UpTime`. Keep `IX_State` as it is. If the new compound index makes it redundant (same
prefix `state`), drop it in a **separate after-release migration** after checking query plans.

**4.** Delete the first (it repeats the code; better name the variable). The second: add a ticket
`// TODO(DEV-NNNNN): ...` or delete. The third is a valid "why" comment; shorten:
`// Progress service ignores archived scopes, so including them loops forever`.

**5.** Expected findings for monolith vs smartcat-ai-agents: private method casing, Async suffix,
global vs per-file nullable, test naming, analyzer severity.

</details>

---

## Summary

- The repo `.editorconfig` and the file you edit win over general guides and personal taste.
- Monolith/PTS: private methods `camelCase`; private fields and constants `_camelCase`.
- Mongo models: `sealed`, `required` + `init`, explicit camelCase `[BsonElement]`,
  `[BsonRequired]`, enums as strings.
- Keep DB entity, API request and API response as separate types.
- New indexes: `IDX_` / `UDX_` with field names; never rename existing `IX_` indexes.
- `IOptions<T>` instead of `IConfiguration` in business classes; validate on start.
- Exceptions are for failures, not for "false". Use Try methods or results (D8 is MAJOR).
- No magic numbers; use `TimeSpan` constants or options for durations.
- Code is self-descriptive: inline comments only for a non-obvious why; `///` 1–2 lines.
- `TreatWarningsAsErrors` + nullable turn whole bug classes into compile errors.

Anki deck: anki/02-code-style.txt

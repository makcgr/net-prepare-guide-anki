# 13. Secure .NET code: OWASP in practice

**Why this chapter matters**

Security questions in a .NET interview are rarely "recite the OWASP Top 10". They are "here is a
controller, what is wrong with it?". The interviewer wants to see if you notice the missing ownership
check, the user-controlled URL, the secret in the code. In real work the same skill matters more: in a
multi-tenant SaaS product one missing filter can show one customer's data to another customer. This
chapter is defensive and review-oriented. It shows how each risk looks in C#, ASP.NET Core and MongoDB
code, how to fix it, how to test it, and how serious it is.

**What you will be able to do**

- Review a C# diff and find the high-impact security bugs in a few minutes, in a fixed order.
- Explain tenant isolation, IDOR and ownership checks, and write the correct check.
- Recognise NoSQL injection, path traversal, SSRF and unsafe deserialization in .NET code and fix them.
- Choose the right crypto primitive: hashing vs password hashing vs key derivation vs encryption.
- Configure secure defaults in ASP.NET Core: HTTPS, HSTS, CORS, antiforgery, data protection, body limits.
- Rate a finding (Critical / Warning / Suggestion, or BLOCKER / MAJOR / MINOR) and defend the rating.

---

## 13.1 The map: OWASP Top 10 and how this chapter uses it

OWASP (Open Worldwide Application Security Project) publishes a list of the ten most common web
application risk categories. The Smartcat security review checklist uses the **2021** edition and
focuses on the categories that appear most often in C# backend diffs:

| Code | Category | Typical .NET example |
|---|---|---|
| A01 | Broken Access Control | `GetById(id)` without an ownership check; missing `[Authorize]` |
| A02 | Cryptographic Failures | `MD5` for passwords; hard-coded API key; `System.Random` for tokens |
| A03 | Injection | User string concatenated into a `BsonDocument` filter; `Path.Combine` with user input |
| A05 | Security Misconfiguration | `ex.ToString()` in the response; `AllowAnyOrigin()` |
| A07 | Identification and Authentication Failures | JWT decoded but not validated |
| A09 | Security Logging and Monitoring Failures | PII in logs; no audit entry for a permission change |
| A10 | Server-Side Request Forgery (SSRF) | `HttpClient.GetAsync(request.Url)` |

The other three 2021 categories also appear in this chapter, but inside other sections:

- **A04 Insecure Design** — covered by threat modelling (13.2) and tenant isolation (13.3).
- **A06 Vulnerable and Outdated Components** — covered by supply-chain hygiene (13.13).
- **A08 Software and Data Integrity Failures** — unsafe deserialization is formally here; this chapter
  discusses it next to injection (13.6) because it looks like injection in a review.

Tip: OWASP published a newer edition in 2025 that reorders the list (for example, SSRF moves into
Broken Access Control and supply-chain failures get their own category). The ideas in this chapter do
not change. In an interview, say which edition you mean if you use the codes.

### Two severity scales you will meet

There are two review skills behind this chapter, and they use two scales. They map well enough:

| OWASP checklist | Rule-based review (S1–S22) | Meaning | Effect on the MR |
|---|---|---|---|
| Critical | BLOCKER | Exploitable or data-leaking; must be fixed before merge | `changes_requested` |
| Warning | MAJOR | Real weakness, needs a fix or an explicit decision | `needs_review` |
| Suggestion | MINOR | Hardening or consistency | `needs_review` or comment |
| — | No findings | — | `approved` |

The severity logic is simple: **any Critical → changes requested**; only Warnings/Suggestions → needs
review; nothing → approved.

**At Smartcat:** the checklist also has an exclusion table. It is not about "tests do not matter". It
is about the real exposure of the code:

| File pattern | Rule |
|---|---|
| `test-workflows/**` | Skip entirely — security team policy, no findings |
| `*Tests.cs`, `*Tests/**`, `*.test.ts`, `*.spec.ts` | Downgrade Critical → Warning |
| `*Migration.cs` | Downgrade Critical → Warning |
| `*Example*`, `*Sample*`, `*Mock*` | Downgrade Warning → Suggestion |

Why downgrade, not skip: a hard-coded secret in a test file is still a leaked secret if it is a real
one. It is less likely to be real, so the rating is lower, but the finding stays visible.

---

## 13.2 Threat modelling in 10 minutes: STRIDE

**Concept.** A threat model answers four questions: what are we building, what can go wrong, what do
we do about it, did we do a good job. STRIDE is a checklist for the second question. Each letter is a
class of threat, and each class breaks one security property.

| Letter | Threat | Property broken | .NET / SaaS example | Typical control |
|---|---|---|---|---|
| S | Spoofing | Authentication | Forged JWT; actor id read from the request body | Validate tokens; take identity from the principal |
| T | Tampering | Integrity | Client sends `isAdmin: true` or a feature flag in the body | Server-side decisions; signed data |
| R | Repudiation | Non-repudiation | "I never deleted that project" and there is no audit entry | Structured audit log |
| I | Information disclosure | Confidentiality | Cross-tenant read; stack trace in a 500 response | Tenant filter; ProblemDetails |
| D | Denial of service | Availability | Unbounded request body; regex with catastrophic backtracking | Size limits, timeouts, rate limits |
| E | Elevation of privilege | Authorization | Freelancer role reaches a manager-only endpoint | Policy-based authorization for every role |

**Why.** Code review finds bugs in lines that exist. Threat modelling finds the lines that are
missing — for example, "this new background job reads files, but who checks that the file belongs to
the workspace?".

**A 10-minute recipe for a feature or an MR:**

1. Draw the data flow: actors, entry points (HTTP, Kafka, background tasks), data stores, external calls.
2. Mark the **trust boundaries** — places where data crosses from less trusted to more trusted
   (browser → API, API → sidecar, other service → your Kafka consumer).
3. For every arrow that crosses a boundary, walk the six STRIDE letters and ask one question each.
4. Write down the top 3 risks and the control for each. Put them in the MR description.

```mermaid
flowchart LR
    U[Browser / API client] -- JWT + JSON --> API[ASP.NET Core API]
    API -- tenant-scoped query --> DB[(MongoDB)]
    API -- user-supplied URL? --> EXT[External site]
    API -- path with workspaceId --> SC[Python sidecar]
    K[Kafka] -- event --> C[Consumer]
    C --> DB
    classDef boundary stroke-dasharray: 5 5
```

Common mistake: treating internal callers as trusted. A Kafka event or an internal HTTP call can carry
an `accountId` that came from a user three hops earlier. The trust boundary is where the data came
from, not where the network packet came from.

Tip: in an interview, if you are asked to design a feature, spend one minute on STRIDE out loud. It is
a cheap and strong Senior signal.

---

## 13.3 Multi-tenant isolation: the number one SaaS risk

**Concept.** Smartcat is a multi-tenant system: many customers (workspaces/accounts) share the same
services and the same MongoDB collections. Every document carries a tenant identifier
(`AccountId`, `WorkspaceId`, `TenantId` or similar). **Tenant isolation** means every read and every
write is limited to the caller's tenant.

The classic bug is **IDOR** (Insecure Direct Object Reference): the API accepts an id and returns the
object without checking that the caller may see it. Ids that are GUIDs make the attack harder but do
not fix it — ids leak through URLs, logs, shared links and support tickets.

**Why it is number one.** Most other bugs hurt one user. A cross-tenant read hurts a customer that
did nothing wrong, it is a reportable data breach, and it destroys trust in a B2B product. It is also
easy to introduce: one new repository method without the filter is enough.

### The three forms of the check

1. **Tenant filter in the query** — the database never returns other tenants' data.
2. **Ownership check after retrieval** — when the lookup cannot include the tenant (for example, an
   unscoped API or a cache), compare the tenant on the result.
3. **Scoped pre-check before an unscoped call** — list the caller's resources first, then call the
   detail API only for an id from that list.

```csharp
// BAD: any authenticated user can read any project if they know the id.
public Task<Project?> GetProjectAsync(Guid projectId, CancellationToken ct) =>
    _projects.Find(x => x.Id == projectId).FirstOrDefaultAsync(ct);

// GOOD (form 1): the tenant comes from the authenticated context, not from the request.
public Task<Project?> GetProjectAsync(Guid projectId, CancellationToken ct)
{
    var accountId = _userContext.GetRequiredAccountId();
    var filter = Builders<Project>.Filter.Eq(x => x.AccountId, accountId)
               & Builders<Project>.Filter.Eq(x => x.Id, projectId);
    return _projects.Find(filter).FirstOrDefaultAsync(ct);
}
```

```csharp
// GOOD (form 2): ownership check after retrieval, for a source that cannot filter by tenant.
var file = await _driveClient.GetFileAsync(driveFileId, ct);
if (file is null || file.WorkspaceId != _userContext.GetRequiredWorkspaceId())
{
    throw new NotFoundException();   // 404, not 403: do not confirm that the id exists
}
```

```csharp
// GOOD (form 3, rule S14): scoped pre-check, then the unscoped detail call.
var ownTms = await _tmClient.ListTmsAsync(accountId, ct);
if (!ownTms.Any(tm => tm.Id == tmId))
{
    throw new ForbiddenException();
}
var details = await _tmClient.GetTmMetadataAsync(tmId, ct);
```

Tip: return **404** for "exists but not yours" when the id itself is sensitive. A 403 tells the caller
"this id is real". Both are acceptable; be consistent and know why you chose one.

### The rules from real past findings

| Rule | What was found | Severity |
|---|---|---|
| `tenant-filter` | MongoDB query filter without `AccountId`/`TenantId` | Critical |
| `ownership-check` | `GetById(id)` result not compared with the caller's account | Critical |
| S2 | `workspaceId`, `accountId`, `projectId`, `driveFileId` taken from the request and never compared with the authenticated context | BLOCKER |
| S3 | Sidecar or storage path keyed only by `conversationId` — two tenants can collide or guess paths | BLOCKER |
| S13 | Route accepts `{workspaceId}` as a free `string` without format validation | BLOCKER |
| S14 | Tool takes `projectId`/`tmId`/`glossaryId` and calls an unscoped metadata API directly | BLOCKER |
| S18 | Credential chain `ByUser ?? ByWorkspace ?? ByOrg` stops at a disabled or empty row | MAJOR |

**S3 — namespace storage by tenant.** A storage key or sidecar path like `/{conversationId}/{fileName}`
has one namespace for all tenants. Include both the tenant and the conversation:

```csharp
// BAD
var path = $"/{conversationId}/{fileName}";

// GOOD: tenant first, then the conversation; each segment validated and encoded (see S9).
var path = $"/{Uri.EscapeDataString(workspaceId)}/{Uri.EscapeDataString(conversationId)}/{Uri.EscapeDataString(fileName)}";
```

**S13 — validate the tenant id format, fail closed.** A free-form string id flows into paths, cache
keys and log lines. Validate the format at the edge:

```csharp
// GOOD: route constraint rejects malformed ids before the action runs.
[HttpGet("workspaces/{workspaceId:guid}/projects")]
public Task<IActionResult> List(Guid workspaceId, CancellationToken ct) => ...;
```

If the canonical id is not a GUID, use a `regex(...)` route constraint or a first-line guard such as
`if (!WorkspaceId.IsValid(id)) return BadRequest();`.

**S18 — the credential chain.** This one is subtle:

```csharp
// BAD: a disabled user-level credential "wins" and blocks the valid workspace one,
// or an empty row returns a credential with no secret.
var credential = FindByUser(userId) ?? FindByWorkspace(workspaceId) ?? FindByOrg(orgId);

// GOOD: filter inactive and empty entries at every level of the chain.
var credential = FindActive(byUser) ?? FindActive(byWorkspace) ?? FindActive(byOrg);

static Credential? FindActive(IEnumerable<Credential> candidates) =>
    candidates.FirstOrDefault(c => c.IsEnabled && !c.IsEmpty);
```

The security effect depends on the direction: sometimes the bug denies service, sometimes it
uses a broader scope than intended. Both are wrong.

### `auth-all-roles`: every role, not only admin and manager

A permission check often lists the roles the author had in mind. Smartcat has more principals:
managers, admins, freelancers/vendors, external users, anonymous users of shared links. The checklist
rule `auth-all-roles` (Critical) asks: did the author decide what **each** role gets?

```csharp
// BAD: freelancers and external users are not mentioned, so they "pass" by default.
if (user.Role is Role.Admin or Role.Manager && !project.AllowEdit) return Forbid();

// GOOD: allow-list. Anything not listed is denied.
if (!CanEdit(user, project)) return Forbid();

static bool CanEdit(User user, Project project) => user.Role switch
{
    Role.Admin or Role.Manager => true,
    Role.Freelancer => project.AssigneeIds.Contains(user.Id),
    _ => false,
};
```

**How to test tenant isolation.** One test per entry point, with two tenants:

```csharp
[Test]
public async Task Should_return_not_found_when_project_belongs_to_another_account()
{
    // Arrange
    var otherAccountProject = await SeedProjectAsync(accountId: OtherAccountId);
    SetCurrentUser(accountId: MyAccountId);

    // Act
    var result = await _service.GetProjectAsync(otherAccountProject.Id, CancellationToken.None);

    // Assert
    Assert.That(result, Is.Null);
}
```

Common mistake: testing only the "happy" tenant. A test with one tenant cannot fail on a missing
tenant filter. The second tenant is the whole point.

Tip: when you review, search the diff for every new `Find(`, `GetById`, `UpdateOne`, `DeleteMany`
and read the filter. It is mechanical, and it finds the most expensive bug class.

---

## 13.4 A01 Broken Access Control: authorization in ASP.NET Core

### Missing `[Authorize]` on write endpoints (S20, `missing-auth-endpoint`)

**Concept.** Every `POST`/`PUT`/`DELETE`/`PATCH` action needs authentication and an authorization
decision. In ASP.NET Core this is `[Authorize]` on the action or controller, or a **fallback policy**
that applies to every endpoint without metadata.

```csharp
// BAD: new write action, no [Authorize], and the actor comes from the body.
[HttpPost("projects/{id:guid}/archive")]
public async Task<IActionResult> Archive(Guid id, ArchiveRequest request)
{
    await _projects.ArchiveAsync(id, archivedByUserId: request.UserId);
    return NoContent();
}

// GOOD: authorized, and the actor identity is taken from the authenticated principal.
[Authorize(Policy = Policies.ProjectManager)]
[HttpPost("projects/{id:guid}/archive")]
public async Task<IActionResult> Archive(Guid id, CancellationToken ct)
{
    await _projects.ArchiveAsync(id, archivedByUserId: User.GetUserId(), ct);
    return NoContent();
}
```

Secure default — deny unless marked otherwise:

```csharp
builder.Services.AddAuthorization(options =>
{
    options.FallbackPolicy = new AuthorizationPolicyBuilder()
        .RequireAuthenticatedUser()
        .Build();
});
// Public endpoints now need an explicit [AllowAnonymous], which is easy to see in review.
```

Common mistake: `UpdatedByUserId`, `OwnerId`, `ActorId` in a request DTO. This is **spoofing**: the
client chooses who it is. Identity comes from `User` / the user context, never from the body.

Tip: `[AllowAnonymous]` overrides `[Authorize]` on the same endpoint. In a review, treat every new
`[AllowAnonymous]` as a question that needs an answer.

### Feature flags from the request body (S1) and snapshotted into BSON (S4)

**Concept.** A feature flag is an authorization decision in disguise: "is this account allowed to use
AI PDF processing?". If the client sends the flag, the client decides.

```csharp
// BAD (S1, BLOCKER): the client controls the feature decision.
var enabled = request.AccountFeatures.GetValue<bool>("IsAiPdfProcessingEnabled");

// GOOD: server-side resolution for the authenticated tenant.
var enabled = await _features.IsAiPdfProcessingAvailable(
    _userContext.UserId!, _userContext.WorkspaceId!, _userContext.OrganizationId!);
```

S4 (MAJOR) is the slower version of the same bug: a new field like `IsAiPdfEnabled` on `AgentRun`
or `Conversation`, stored in MongoDB at creation time. When the admin switches the flag off, old runs
still have `true`. Re-resolve the flag on every read; a background job gets the `accountId` and
evaluates the flag itself.

**At Smartcat:** in `smartcat-ai-agents`, server-side flags live behind
`src/Module/Services/IFeatureService.cs`. The middleware that reads `account_features` from AG-UI
`forwardedProps` is the intended entry point for UI hints; the review rule flags what happens
**downstream** (deciding access from it, snapshotting it), not the middleware itself.

### Mutable ambient state (S5)

```csharp
// BAD (S5, MAJOR): any code can write the "current tenant" for the whole async flow.
public static class CurrentTenant
{
    public static readonly AsyncLocal<string?> Value = new();
}
```

Why it is a security issue: `AsyncLocal` values flow into child tasks and background work. A value set
in one place can leak into work for another request, or be changed by code that should not own it.
Use scoped DI (`AddScoped<IUserContext, UserContext>()`) or `HttpContext.Items` keyed once per request.
See chapter 03 (Async and await) for how `ExecutionContext` flows.

**At Smartcat:** `smartcat-ai-agents/src/Module.Mcp/Auth/PlatformUserContext.cs` is the canonical
tenant identity. It does use `AsyncLocal` inside, but it has clear owners (the auth middleware for web
requests, the task processor for background runs) and a fail-closed accessor
`GetRequiredWorkspaceId()` that throws on a missing or empty id. The rule targets ad-hoc ambient state
without a scope owner. Cross-tenant comparisons must use this context.

### CORS and directory listing (Warnings)

`cors-misconfiguration` and `directory-listing` are A01 Warnings in the checklist. CORS is covered with
the other secure defaults in 13.7.

---

## 13.5 A02 Cryptographic failures

### Choose the right primitive

Most crypto bugs in application code are "right algorithm, wrong job". Learn this table:

| Job | Use | Never use |
|---|---|---|
| Integrity fingerprint of non-secret data | `SHA256.HashData` | `MD5`, `SHA1` for anything security-related |
| Store a user password | ASP.NET Core Identity `PasswordHasher<T>`, PBKDF2, Argon2id | `SHA256(password)`, even with salt |
| Derive an encryption key from a passphrase | PBKDF2 (`Rfc2898DeriveBytes.Pbkdf2`) with high iterations, or Argon2id | `SHA256.HashData(passphrase)` |
| Derive sub-keys from an already random key | HKDF (`HKDF.DeriveKey`) | Concatenate and hash by hand |
| Encrypt data | `AesGcm` (authenticated), or Data Protection API | `DES`, `TripleDES`, `RC2`, `RC4`, AES-ECB, AES-CBC without a MAC |
| Message authentication | `HMACSHA256` | Plain hash of `secret + message` |
| Tokens, nonces, ids that must not be guessed | `RandomNumberGenerator` | `System.Random`, `Guid.NewGuid()` as a secret |
| Compare secrets | `CryptographicOperations.FixedTimeEquals` | `==` / `SequenceEqual` (timing leak) |

Checklist rules: `weak-hash` (Critical), `weak-crypto` (Critical), `random-not-crypto` (Warning).

Why `System.Random` is wrong for tokens: it is a fast, predictable generator. With a few outputs, the
next ones can be predicted. `Guid.NewGuid()` is random in practice on modern .NET, but it is not
specified as a security token, it has only 122 random bits, and its format invites people to log it.

```csharp
// BAD
var resetToken = new Random().Next().ToString();

// GOOD: 256 bits from the OS cryptographic generator, URL-safe.
var resetToken = WebEncoders.Base64UrlEncode(RandomNumberGenerator.GetBytes(32));
```

### Key derivation: never `SHA256(passphrase)` (S16)

**Concept.** A passphrase has low entropy. A fast hash lets an attacker test billions of guesses per
second. A key derivation function (KDF) for passwords is slow on purpose and uses a salt so that equal
passphrases give different keys.

```csharp
// BAD (S16, MAJOR): fast hash, no salt, same passphrase = same key everywhere.
var key = SHA256.HashData(Encoding.UTF8.GetBytes(passphrase));
using var aes = Aes.Create();
aes.Key = key;

// GOOD: PBKDF2 with a per-key random salt, stored next to the ciphertext.
byte[] salt = RandomNumberGenerator.GetBytes(16);
byte[] key = Rfc2898DeriveBytes.Pbkdf2(
    password: passphrase,
    salt: salt,
    iterations: 600_000,
    hashAlgorithm: HashAlgorithmName.SHA256,
    outputLength: 32);
```

**PBKDF2 vs HKDF** — a common interview probe:

- **PBKDF2 / Argon2id**: input is a *password* (low entropy). Slow by design.
- **HKDF**: input is already a *strong random key* (high entropy). Fast, used to derive several keys
  from one master key (`info` parameter separates purposes).

```csharp
// HKDF: one master key, separate keys per purpose.
byte[] encryptionKey = HKDF.DeriveKey(HashAlgorithmName.SHA256, masterKey, 32,
    salt: null, info: "drive-file-encryption-v1"u8.ToArray());
```

Also part of S16: document the `keyId` rotation contract. Store `{keyId, salt, nonce, ciphertext,
tag}` together, so you can decrypt old data after the key changes.

### Authenticated encryption with `AesGcm`

```csharp
public static byte[] Encrypt(byte[] key, byte[] plaintext, byte[] associatedData)
{
    var nonce = RandomNumberGenerator.GetBytes(AesGcm.NonceByteSizes.MaxSize); // 12 bytes
    var ciphertext = new byte[plaintext.Length];
    var tag = new byte[16];
    using var aes = new AesGcm(key, tagSizeInBytes: 16);
    aes.Encrypt(nonce, plaintext, ciphertext, tag, associatedData);
    return [.. nonce, .. tag, .. ciphertext];
}
```

Common mistake: reusing a nonce with the same key in GCM. It breaks confidentiality and integrity.
Use a random 12-byte nonce per message (fine for realistic message counts per key) and rotate keys.

Tip: in an interview, "I would not write this myself; I would use the Data Protection API or a KMS
envelope scheme" is a strong answer — as long as you can also explain what the library does.

### Hard-coded secrets (`hardcoded-secret`, Critical)

```csharp
// BAD
private const string ApiKey = "sk-live-...";
var client = new MongoClient("mongodb://admin:password@...");
```

A secret in Git is leaked for ever: it stays in history, forks, CI caches and local clones. The fix is
two steps: **rotate the secret first**, then remove it from the code. Removing it from the code alone
fixes nothing. See 13.11 for where secrets belong.

### TLS: plaintext HTTP and disabled validation (S8)

```csharp
// BAD (S8, BLOCKER): accepts any certificate, so any man-in-the-middle is accepted.
var handler = new HttpClientHandler
{
    ServerCertificateCustomValidationCallback = HttpClientHandler.DangerousAcceptAnyServerCertificateValidator
};

// ACCEPTABLE ONLY for local development, explicitly gated:
if (env.IsDevelopment())
{
    // Local sidecar uses a self-signed certificate; never enabled outside Development.
    handler.ServerCertificateCustomValidationCallback = HttpClientHandler.DangerousAcceptAnyServerCertificateValidator;
}
```

Better than the gate: trust the specific development CA, or use `dotnet dev-certs`. If a staging
certificate is broken, fix the certificate.

`http-plaintext` (Warning): a hard-coded `http://` URL to an **external** service. Local addresses
are fine.

**At Smartcat:** the calibration notes say that internal-network calls (for example, an internal
integration API client on plain HTTP inside the cluster) are not findings by themselves. The finding
is when TLS is **added and then disabled** — that is worse than no TLS, because it looks safe.

### Secret fingerprints (S19, MINOR)

A `*Fingerprint` or `*Hash` field on a secret entity that no code reads is dead weight that suggests a
feature that does not exist. Pick one direction: compare fingerprints and skip re-encryption when equal
(idempotent upsert), or remove the field. If you keep it, use an HMAC with a server key, not a plain
hash — a plain hash of a short API key can be brute-forced.

---

## 13.6 A03 Injection (and unsafe deserialization)

**Concept.** Injection happens when **data** is interpreted as **code or structure**. The cure is
always the same idea: keep data and structure separate. Use typed builders and parameters; never
build the structure from strings.

### NoSQL injection in MongoDB

MongoDB has no SQL, but it has a query *language* (operators like `$ne`, `$gt`, `$where`, `$regex`).
Injection appears in four shapes in C#:

**1. String-built queries.**

```csharp
// BAD (nosql-injection, Critical): the user string becomes part of the query structure.
// A value containing a quote can close the string and add operators.
var filter = BsonDocument.Parse("{ Email: '" + email + "' }");

// GOOD: typed builder; the value is always a value.
var filter = Builders<User>.Filter.Eq(x => x.Email, email);
```

**2. `$where` and server-side JavaScript.**

```csharp
// BAD: arbitrary JavaScript evaluated per document; also slow (no index).
var filter = new BsonDocument("$where", $"this.Name == '{name}'");
```

There is almost never a reason to use `$where` in application code. Use normal operators. If you see
it in a diff, the fix is to remove it.

**3. Operator injection from client JSON.** If a controller accepts a raw `BsonDocument`,
`Dictionary<string, object>` or `JsonElement` and passes it to the driver as a filter, the client can
send `{ "$ne": null }` instead of a string and match every document. Bind to typed DTOs with typed
properties (`string`, `Guid`, enums). A `string` property cannot hold an operator object.

**4. Field-name and regex injection (`expression-injection`, Warning).**

```csharp
// BAD: user chooses the field name — they can sort or filter by "PasswordHash".
var sort = Builders<User>.Sort.Ascending(request.SortBy);

// GOOD: map an allow-list of public names to typed fields.
var sort = request.SortBy switch
{
    "name" => Builders<User>.Sort.Ascending(x => x.Name),
    "created" => Builders<User>.Sort.Descending(x => x.CreatedAt),
    _ => throw new BadRequestException("Unsupported sort field."),
};
```

```csharp
// BAD: user text used as a regex — ".*" matches everything, and a nested pattern
// like "(a+)+$" can make the server spend seconds per document (ReDoS).
var filter = Builders<Project>.Filter.Regex(x => x.Name, new BsonRegularExpression(query, "i"));

// GOOD: escape, anchor, limit the length, and keep the tenant filter.
if (query.Length > 100) throw new BadRequestException("Query is too long.");
var pattern = "^" + Regex.Escape(query);
var filter = Builders<Project>.Filter.Eq(x => x.AccountId, accountId)
           & Builders<Project>.Filter.Regex(x => x.Name, new BsonRegularExpression(pattern, "i"));
```

Tip: an anchored prefix regex (`^abc`) can use an index; an unanchored one scans. Security and
performance agree here. See chapter 09 (MongoDB models, indexes and safe migrations).

### Command injection (`command-injection`, Critical)

```csharp
// BAD: the shell interprets the user string.
Process.Start("bash", $"-c \"convert {fileName} out.pdf\"");

// GOOD: no shell; arguments passed as a list; the file name is our own, not the user's.
var psi = new ProcessStartInfo("convert") { UseShellExecute = false };
psi.ArgumentList.Add(localSafePath);
psi.ArgumentList.Add(outputPath);
using var process = Process.Start(psi)!;
```

`ProcessStartInfo.ArgumentList` passes each argument separately, so spaces and quotes in a value
cannot create new arguments. Even then, do not pass user-chosen file names: store the upload under a
generated name and keep the original name only as metadata.

### Path traversal (`path-traversal` Critical, S9 MAJOR)

**Concept.** `../../etc/passwd` in a file name escapes the intended folder. .NET has a second trap:
`Path.Combine` **discards the root** when the second argument is an absolute path.

```csharp
Path.Combine("/data/uploads", "/etc/passwd");   // returns "/etc/passwd"
Path.Combine("/data/uploads", "../secrets.json"); // returns "/data/uploads/../secrets.json"
```

```csharp
// BAD
var path = Path.Combine(_root, request.FileName);
return File.OpenRead(path);

// GOOD: resolve the full path and check it stays inside the root.
public string ResolveInsideRoot(string root, string relative)
{
    var rootFull = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
    var candidate = Path.GetFullPath(Path.Combine(rootFull, relative));
    if (!candidate.StartsWith(rootFull, StringComparison.Ordinal))
    {
        throw new BadRequestException("Invalid path.");
    }
    return candidate;
}
```

The trailing separator matters: without it, `/data/uploads-evil` would pass a check for
`/data/uploads`. If you only need a file name, `Path.GetFileName(input)` drops every directory part.

**S9 for URLs (sidecar proxies).** The past finding: sanitization checked for `..` on the raw string,
**before** URL decoding. `%2e%2e` passed the check and became `..` later. The correct order:

1. URL-decode first.
2. Split into segments.
3. Reject any segment that is `..`, `.`, empty, or contains `/` or `\`.
4. Re-encode each segment with `Uri.EscapeDataString` and join.

```csharp
public static string SafeRelativePath(string rawPath)
{
    var decoded = Uri.UnescapeDataString(rawPath);
    var segments = decoded.Split('/');
    foreach (var segment in segments)
    {
        if (segment is "" or "." or ".." || segment.Contains('\\'))
        {
            throw new BadRequestException("Invalid path segment.");
        }
    }
    return string.Join('/', segments.Select(Uri.EscapeDataString));
}
```

**At Smartcat:** `smartcat-ai-agents/src/Module/Agents/PdfTranslation/SidecarHttpProxy.cs` is the
pass-through to the Python PDF sidecar. The review skill names it as a place where path traversal and
TLS shortcuts have lived before, so changes there get extra attention.

### Log injection (`log-injection`, Warning)

If a user string with a newline goes into a plain-text log, the attacker can forge a fake log line
("User admin logged in"). Structured logging helps because values are parameters:

```csharp
// BAD: interpolation builds the message; the value is not a separate field (also CA2254).
_logger.LogInformation($"Login failed for {userName}");

// GOOD: message template; sinks store userName as a field.
_logger.LogInformation("Login failed for {UserName}", userName);
```

Plain-text console sinks can still print the newline. For values from users, keep them as template
parameters and avoid putting them in the message text itself.

### Unsafe deserialization (formally A08)

```csharp
// BAD: the JSON chooses the .NET type to create — a known remote code execution vector.
var settings = new JsonSerializerSettings { TypeNameHandling = TypeNameHandling.All };
var obj = JsonConvert.DeserializeObject(body, settings);
```

Rules:

- Never use `TypeNameHandling` other than `None` for data you do not fully control. If you need
  polymorphism, use a `SerializationBinder` with an allow-list, or System.Text.Json
  `[JsonDerivedType]` with explicit type discriminators.
- `BinaryFormatter` is obsolete and, since .NET 9, its implementation is removed (it throws). Treat any
  usage in old code as a finding.
- In MongoDB, the C# driver's discriminator (`_t`) maps only to registered class maps. Still, do not
  deserialize client-sent BSON into `object`.

### Untrusted JSON (S6, MAJOR)

```csharp
// BAD: throws InvalidOperationException when the value is a string "true" or null → 500.
var enabled = element.GetProperty("enabled").GetBoolean();

// GOOD: check ValueKind first; treat anything unexpected as "not set".
var enabled = element.TryGetProperty("enabled", out var value)
              && value.ValueKind == JsonValueKind.True;
```

Also set `JsonSerializerOptions.MaxDepth` (for example 32) for untrusted input. The default is 64;
deeply nested input costs stack and CPU, and a smaller limit makes the contract explicit.

Common mistake: thinking "it only throws, so it is safe". An exception becomes a 500, the 500 may leak
details (13.7), and an attacker who can make every request fail has a cheap denial of service.

---

## 13.7 A05 Security misconfiguration and secure defaults in ASP.NET Core

### Do not return internals (`stack-trace-exposure` Critical, `debug-info-exposed` Warning)

```csharp
// BAD: stack trace, file paths, connection details, Mongo error text — all public.
catch (Exception ex)
{
    return StatusCode(500, ex.ToString());
}

// GOOD: central handler, ProblemDetails, a correlation id, details only in logs.
builder.Services.AddProblemDetails();
builder.Services.AddExceptionHandler<GlobalExceptionHandler>();
app.UseExceptionHandler();

public sealed class GlobalExceptionHandler(ILogger<GlobalExceptionHandler> logger) : IExceptionHandler
{
    public async ValueTask<bool> TryHandleAsync(HttpContext context, Exception exception, CancellationToken ct)
    {
        logger.LogError(exception, "Unhandled exception. TraceId {TraceId}", context.TraceIdentifier);
        context.Response.StatusCode = StatusCodes.Status500InternalServerError;
        await context.Response.WriteAsJsonAsync(new ProblemDetails
        {
            Status = 500,
            Title = "Unexpected error.",
            Extensions = { ["traceId"] = context.TraceIdentifier },
        }, ct);
        return true;
    }
}
```

`ex.Message` is also a risk when it can contain internals: `InnerException.Message` from the driver
may include host names or query fragments. Validation messages written by you for the client are fine.

`sensitive-field-serialized` (Warning): a response DTO that exposes `PasswordHash`, an internal secret,
a system id or a raw exception. Fix: separate response DTOs; never serialize the domain/storage entity
directly. `default-credentials` (Warning): template values like `admin/admin` or `changeme` left in
config.

### HTTPS, HSTS and forwarded headers

```csharp
if (!app.Environment.IsDevelopment())
{
    app.UseHsts();          // tells browsers: only HTTPS for this host, for max-age
}
app.UseHttpsRedirection();
```

Behind an ingress that terminates TLS, the app sees plain HTTP. Configure `ForwardedHeadersOptions`
with the known proxy networks so `Request.Scheme` is correct. Do not trust `X-Forwarded-*` from any
source: an unrestricted config lets a client fake its IP address and scheme.

### CORS (`cors-misconfiguration`, Warning)

```csharp
// BAD: reflects any origin AND allows cookies — any site can call the API as the user.
policy.SetIsOriginAllowed(_ => true).AllowCredentials();

// GOOD: explicit allow-list from configuration.
builder.Services.AddCors(o => o.AddPolicy("Frontend", policy => policy
    .WithOrigins(corsOptions.AllowedOrigins)
    .WithMethods("GET", "POST", "PUT", "DELETE")
    .WithHeaders("Content-Type", "Authorization")
    .AllowCredentials()));
```

Note: `AllowAnyOrigin()` together with `AllowCredentials()` throws at startup — the framework blocks
that combination. People then use `SetIsOriginAllowed(_ => true)` to "fix" the error, which is the
same hole without the protection. CORS is a browser feature; it does not protect the API from
server-to-server calls. It is not access control.

### Antiforgery (CSRF)

CSRF (cross-site request forgery): another site makes the browser send a request with the user's
cookies. It matters when **authentication is a cookie**. With a bearer token in the `Authorization`
header, the browser does not attach it automatically, so CSRF does not apply in the same way.

```csharp
builder.Services.AddAntiforgery();
app.UseAntiforgery();   // .NET 8+: validates tokens for form posts on endpoints that require it
```

Also use `SameSite=Lax` or `Strict` cookies as a second layer.

**At Smartcat:** the monolith has dedicated antiforgery tests for admin endpoints, for example
`smartcat/WebApplication/Tests/AdminApp.WebModule.Tests/Controllers/AgentPlatformMcpCreateDraftAntiforgeryTests.cs`.
This is a good pattern: a security property that is easy to lose in a refactoring gets a test.

### Data Protection

ASP.NET Core Data Protection encrypts auth cookies, antiforgery tokens and anything you protect with
`IDataProtector`. By default keys are stored locally. With several replicas, each pod has different
keys, and cookies fail randomly after a restart or on another pod.

```csharp
builder.Services.AddDataProtection()
    .SetApplicationName("project-tasks")         // same name on every replica
    .PersistKeysToStackExchangeRedis(redis, "DataProtection-Keys");
```

Choose a shared key store, protect the keys at rest where possible, and do not share one application
name between unrelated services.

### Request body limits: denial of service (S7, S22)

```csharp
// BAD (S7): buffers the whole body in memory, no size check.
context.Request.EnableBuffering();
using var reader = new StreamReader(context.Request.Body);
var body = await reader.ReadToEndAsync();

// BAD (S22): proxy copies an arbitrary upload into a MemoryStream.
var buffer = new MemoryStream();
await Request.Body.CopyToAsync(buffer);
```

```csharp
// GOOD: per-route cap and a 413 response; stream instead of buffering.
const long MaxBytes = 10 * 1024 * 1024;
if (context.Request.ContentLength is null or > MaxBytes)
{
    context.Response.StatusCode = StatusCodes.Status413PayloadTooLarge;
    return;
}
context.Features.Get<IHttpMaxRequestBodySizeFeature>()!.MaxRequestBodySize = MaxBytes;
await context.Request.Body.CopyToAsync(upstreamStream, context.RequestAborted); // stream, do not buffer
```

`ContentLength` can be missing (chunked transfer), so do not trust it alone; the Kestrel feature
enforces the limit while reading. For MVC actions use `[RequestSizeLimit(...)]` and
`[RequestFormLimits(MultipartBodyLengthLimit = ...)]`. Kestrel's global default is about 30 MB — set
smaller limits per route that does not need large bodies. If you must buffer, use
`EnableBuffering(bufferThreshold, bufferLimit)` with explicit numbers, never `int.MaxValue`.

Why S7/S22 are "security": memory is shared by all tenants on the pod. One large request can push the
pod out of memory and stop the service for everyone.

### JWT event handlers inline in startup (S21, MAJOR)

A 40-line lambda in `OnMessageReceived` inside `Program.cs` is hard to test and hard to review, and
auth bugs hide in code that nobody tests. Extract it:

```csharp
builder.Services.AddScoped<JwtBearerEventHandler>();
builder.Services.AddAuthentication().AddJwtBearer(o => o.EventsType = typeof(JwtBearerEventHandler));

public sealed class JwtBearerEventHandler : JwtBearerEvents
{
    public override Task MessageReceived(MessageReceivedContext context)
    {
        // Reads the token from the custom header when the Authorization header is absent.
        context.Token ??= context.Request.Headers["X-Token"].FirstOrDefault();
        return Task.CompletedTask;
    }
}
```

Now `MessageReceived` has a unit test, and the startup file stays declarative.

---

## 13.8 A07 Identification and authentication failures

### Validate the JWT, do not only decode it (`jwt-not-validated`, Critical)

```csharp
// BAD: reads claims, checks nothing. Anyone can create this token.
var token = new JwtSecurityTokenHandler().ReadJwtToken(raw);
var userId = token.Claims.First(c => c.Type == "sub").Value;
```

`ReadJwtToken` parses; it does **not** verify the signature, issuer, audience or expiry. Use the
authentication middleware with strict parameters:

```csharp
builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(options =>
    {
        options.Authority = authOptions.Authority;
        options.TokenValidationParameters = new TokenValidationParameters
        {
            ValidateIssuer = true,
            ValidIssuer = authOptions.Issuer,
            ValidateAudience = true,
            ValidAudience = authOptions.Audience,
            ValidateLifetime = true,
            ValidateIssuerSigningKey = true,
            ValidAlgorithms = [SecurityAlgorithms.RsaSha256],
            ClockSkew = TimeSpan.FromMinutes(1),
        };
    });
```

`ValidAlgorithms` blocks algorithm confusion (for example a token that claims `alg: none` or switches
from RSA to HMAC). The default `ClockSkew` is 5 minutes; reduce it if your clocks are in sync.

### Base64URL, not Base64 (S12, BLOCKER)

A JWT has three parts separated by dots. Each part is **Base64URL**: `-` and `_` instead of `+` and
`/`, and no `=` padding.

```csharp
// BAD: fails with FormatException on many real tokens (depends on the content!),
// and the usual "fix" is a hand-made replace that has its own bugs.
var payloadJson = Encoding.UTF8.GetString(Convert.FromBase64String(raw.Split('.')[1]));

// GOOD
var payloadJson = Base64UrlEncoder.Decode(raw.Split('.')[1]);   // Microsoft.IdentityModel.Tokens
```

Why it is a BLOCKER although it "only" fails: the failure depends on the token content, so it appears
for some users and not others, and it is in the auth path. Tests with one sample token pass. Better
still, do not parse JWTs by hand at all.

**At Smartcat:** the review skill names the platform token reader in `smartcat-ai-agents` (under
`src/Module/Auth/`) as the place where Base64URL handling lives. Bugs there break authentication for
everyone, so changes to it get a dedicated reviewer look.

### Sessions and tokens

- `session-not-invalidated` (Warning): logout must invalidate the session or refresh token on the
  server. Deleting the cookie on the client is not enough if the token stays valid.
- Short-lived access tokens + revocable refresh tokens is the standard compromise.
- `insecure-token-storage` (Warning, front end): see 13.12.

Common mistake: accepting a token from a query string (`?access_token=...`). Query strings are logged
by proxies and stored in browser history. Only accept it where the protocol forces it (for example,
WebSocket/SSE handshakes), and then keep it out of logs.

---

## 13.9 A09 Logging and monitoring failures

Three checks, all Warnings, and one rule from the past-findings list:

| Check | Problem | Fix |
|---|---|---|
| `audit-missing` | Payment, account deletion, permission change, auth event or export without a structured audit entry | Audit event with actor, tenant, target, action, result, time |
| `pii-in-logs` | Email, name, phone, document content in a log message | Log ids, not values; mask where needed |
| `exception-swallowed-silently` | Empty `catch`, or `catch` without logging | Log with context, or let it propagate |
| S11 (MINOR) | `response.Content`, `responseBody` or user document text logged at Information+ | Log status code, duration, request id; bodies at Debug at most, guarded |

```csharp
// BAD
_logger.LogInformation("Invited {Email} with token {Token}", email, inviteToken);
_logger.LogWarning("Upstream failed: {Body}", await response.Content.ReadAsStringAsync(ct));

// GOOD
_logger.LogInformation("Invitation created {InvitationId} for account {AccountId}", invitationId, accountId);
_logger.LogWarning("Upstream failed {StatusCode} in {ElapsedMs} ms, request {RequestId}",
    (int)response.StatusCode, elapsed.TotalMilliseconds, requestId);

if (_logger.IsEnabled(LogLevel.Debug))
{
    _logger.LogDebug("Upstream body {Body}", Truncate(body, 2_000));
}
```

Why logs are a security topic in both directions:

- **Too much** in logs: logs go to a central store with wider access than the database, with long
  retention, sometimes to third parties. PII there is a privacy incident. At Smartcat the content is
  customers' documents, translation memories and glossaries — that is customer data, not "debug info".
- **Too little**: without an audit trail you cannot answer "who changed this permission?" (STRIDE R),
  and without logged security exceptions you will not see an attack in progress.

```csharp
// BAD: the security failure disappears.
try { await _tokenValidator.ValidateAsync(token, ct); }
catch { }

// GOOD: log the fact (not the token), then fail closed.
catch (SecurityTokenException ex)
{
    _logger.LogWarning(ex, "Token validation failed for client {ClientId}", clientId);
    return Results.Unauthorized();
}
```

**At Smartcat:** feature-flag changes are audited in an audit service (see the
`backend-smartcat-audit-feature-history` skill). This is the model for `audit-missing`: a dedicated,
queryable store with actor and scope, not a free-text log line.

---

## 13.10 A10 Server-Side Request Forgery (SSRF)

**Concept.** SSRF means the attacker makes **your server** send a request to a URL they choose. Your
server sits inside the network: it can reach internal services, the cloud metadata endpoint
(`169.254.169.254`), admin ports, localhost. Features that take a URL are the risk: webhooks, "import
from URL", link previews, connectors, an AI agent tool that fetches a page.

```csharp
// BAD (ssrf-user-url, Critical)
var response = await _httpClient.GetAsync(request.SourceUrl, ct);
```

### Layered defence

1. **Allow-list** where you can: known hosts, `https` only, default ports only.
2. **Parse with `Uri`**, require `Uri.IsAbsoluteUri` and scheme `https`; reject user info
   (`user@host`).
3. **Do not follow redirects automatically** (`ssrf-redirect`, Warning): an allowed host can redirect
   to an internal one. Set `AllowAutoRedirect = false` and validate each `Location` yourself.
4. **Check the IP at connect time**, not only the host name at input time (`ssrf-dns-rebind`,
   Warning). DNS rebinding: the name resolves to a public IP when you validate and to `10.0.0.5` when
   you connect. This is a time-of-check / time-of-use bug.
5. **Network egress rules** as the last layer: the pod should not reach what it does not need.

```csharp
var handler = new SocketsHttpHandler
{
    AllowAutoRedirect = false,
    ConnectTimeout = TimeSpan.FromSeconds(5),
    ConnectCallback = async (context, ct) =>
    {
        var addresses = await Dns.GetHostAddressesAsync(context.DnsEndPoint.Host, ct);
        if (addresses.Length == 0 || addresses.Any(IsBlocked))
        {
            throw new HttpRequestException("Destination is not allowed.");
        }

        var socket = new Socket(SocketType.Stream, ProtocolType.Tcp) { NoDelay = true };
        try
        {
            // Connect to the address we checked, not a fresh DNS answer.
            await socket.ConnectAsync(addresses[0], context.DnsEndPoint.Port, ct);
            return new NetworkStream(socket, ownsSocket: true);
        }
        catch
        {
            socket.Dispose();
            throw;
        }
    },
};

static bool IsBlocked(IPAddress address)
{
    if (address.IsIPv4MappedToIPv6) address = address.MapToIPv4();
    if (IPAddress.IsLoopback(address) || address.IsIPv6LinkLocal || address.IsIPv6SiteLocal
        || address.IsIPv6UniqueLocal || address.Equals(IPAddress.Any) || address.Equals(IPAddress.IPv6Any))
    {
        return true;
    }
    if (address.AddressFamily != AddressFamily.InterNetwork) return false;
    var b = address.GetAddressBytes();
    return b[0] == 10                                  // 10.0.0.0/8
        || b[0] == 127                                 // loopback
        || b[0] == 0                                   // "this network"
        || (b[0] == 172 && b[1] is >= 16 and <= 31)   // 172.16.0.0/12
        || (b[0] == 192 && b[1] == 168)                // 192.168.0.0/16
        || (b[0] == 169 && b[1] == 254)                // link-local, cloud metadata
        || (b[0] == 100 && b[1] is >= 64 and <= 127);  // carrier-grade NAT, often internal
}
```

Register the handler for a **named** `HttpClient` used only for user-supplied URLs, so internal
clients keep their normal configuration. See chapter 05 (ASP.NET Core) for `IHttpClientFactory`.

Common mistake: a deny-list of strings (`if (url.Contains("localhost"))`). There are many ways to write
the same address (`127.1`, decimal IPs, IPv6, DNS names that resolve to private ranges). Check the
resolved IP address, not the text.

Tip: also limit response size and time. A URL that returns an endless stream is an SSRF-shaped DoS.

---

## 13.11 Secrets management

**Concept.** A secret is anything that grants access: API keys, connection strings with passwords,
signing keys, encryption keys, S2S credentials. Rules:

1. Never in source code, never in committed config (`hardcoded-secret`, Critical).
2. Injected at runtime by the platform (Kubernetes secrets, a vault), read through configuration.
3. Typed and validated at startup (S10, S17).
4. Rotatable without a code change; rotated at once when leaked.
5. Never logged, never returned in a response, never stored in the front-end bundle.

### Typed options, validated at startup (S10 MINOR, S17 MAJOR)

```csharp
// BAD (S10): raw IConfiguration in business logic; typos fail at runtime, on the first request.
public sealed class Encryptor(IConfiguration config)
{
    private readonly string _key = config["Encryption:Key"]!;
}

// BAD (S17): the "config check" runs inside a service method, so a broken deployment looks healthy.
```

```csharp
// GOOD: strongly typed, validated, fail fast at startup.
public sealed class EncryptionOptions
{
    [Required, MinLength(44)] public string MasterKey { get; init; } = "";
    [Required] public string KeyId { get; init; } = "";
}

builder.Services.AddOptions<EncryptionOptions>()
    .Bind(builder.Configuration.GetSection("Encryption"))
    .ValidateDataAnnotations()
    .Validate(o => IsBase64(o.MasterKey), "Encryption:MasterKey must be base64.")
    .ValidateOnStart();

public sealed class Encryptor(IOptions<EncryptionOptions> options) { /* ... */ }
```

Why fail fast: a pod with a missing key that starts, passes health checks and fails on the first real
request is worse than a pod that never becomes ready. The rollout stops, the old version keeps
working, and the log line tells you exactly which key is missing.

**At Smartcat:** services use layered JSON configuration (`.configurations/common.json` →
`.configurations/{environment}/common.json` → local `override.dev.json`, which is git-ignored). In
deployed environments the secret values are, as far as this book's sources show, provided by
Kubernetes secrets and merged on top. Two practical rules follow: a template file like
`override.dev.template.json` must contain placeholders only (`default-credentials`), and a new
configuration key for production must exist in every production region's configuration. See
chapter 05 (ASP.NET Core) and chapter 06 (Architectural patterns at Smartcat) for the config layers.

### Local development

Use `dotnet user-secrets` or a git-ignored override file. Before every commit, check that no real value
went into a tracked file. If a secret was pushed, assume it is compromised: rotate it, then clean
history if policy requires.

### Front-end bundles

Everything in a front-end bundle is public. In Vite, every `import.meta.env.VITE_*` value is inlined
into the JavaScript. `VITE_API_KEY` is therefore a published key (rule FS4). Secrets stay on the
backend; the browser calls a backend endpoint that holds the secret.

---

## 13.12 Front-end cross-over: XSS and tokens in storage

A backend engineer is often asked about these in a full-stack review:

| Rule | Bad pattern | Fix | Severity |
|---|---|---|---|
| FS1 | `v-html` bound to LLM output, `marked(...)` result, HTTP response or user input | `DOMPurify.sanitize(...)` in one shared helper | BLOCKER |
| FS2 | `el.innerHTML = ...`, `document.write(...)` | Framework bindings; sanitize when HTML is required | BLOCKER |
| FS3 | API key literals in `*.ts` / `*.vue` | Backend proxy | BLOCKER |
| FS5 | URLs built by string concatenation from user input; `window.location.href = userValue` | `new URL(...)` + allow-list of paths | MAJOR |
| FS9 / `insecure-token-storage` | Tokens in `localStorage` / `sessionStorage` | `httpOnly` cookie, or in memory only | MAJOR / Warning |
| FS10 | `DOMPurify.sanitize(html)` without an explicit allow-list config | Helper with `ALLOWED_TAGS` / `ALLOWED_ATTR` | MINOR |

**Why tokens in `localStorage` are a problem.** Any script on the page can read `localStorage`. One
XSS bug — in your code or in any dependency — and the attacker has a token they can use from their own
machine. An `httpOnly` cookie cannot be read by script. XSS is still bad with cookies, but the attacker
must act inside the victim's browser session, which is much more limited. Cookies bring CSRF back,
which is why antiforgery and `SameSite` (13.7) go together with this choice.

**Why markdown from an LLM is an XSS source.** Model output can contain HTML, and the model can be
instructed by content it read (prompt injection). Treat LLM output exactly like user input.

**The backend part of XSS:** set `Content-Type` correctly (`application/json`, not `text/html`) for API
responses, send `X-Content-Type-Options: nosniff`, and use a Content Security Policy for pages you
serve.

---

## 13.13 Dependency and supply-chain hygiene

Your code is a small part of what runs in production. NuGet and npm packages, base images and build
tools are code you did not review. (OWASP 2021 A06 / A08.)

### Vulnerable packages

```bash
dotnet list package --vulnerable --include-transitive
```

Since .NET 8, `dotnet restore` runs **NuGet Audit** and reports known vulnerabilities as warnings
(`NU1901`–`NU1904` by severity). Make it fail the build for high and critical issues:

```xml
<PropertyGroup>
  <NuGetAudit>true</NuGetAudit>
  <NuGetAuditMode>all</NuGetAuditMode>      <!-- include transitive packages -->
  <NuGetAuditLevel>moderate</NuGetAuditLevel>
  <WarningsAsErrors>$(WarningsAsErrors);NU1903;NU1904</WarningsAsErrors>
</PropertyGroup>
```

A transitive vulnerability is fixed by adding a direct reference to the patched version (with Central
Package Management, `CentralPackageTransitivePinningEnabled`), not by waiting for the parent package.

### Pre-release and floating versions

| Pattern | Why it is a risk | What to ask in review |
|---|---|---|
| `Version="2.0.0-beta.3"` in a production service | No stability or security-fix promise; may be abandoned | Why is the stable version not enough? Who owns the upgrade? |
| `Version="1.*"` (floating) | A new upload changes your build without a diff | Pin exact versions; use lock files |
| An internal fork like `x.y.z-company.N` | By SemVer it is a pre-release; fine if owned | Is there an owner, a reason, and a plan to return to upstream? |
| A new package with few downloads, one maintainer | Typosquatting, takeover risk | Is it the real package? Can we avoid it? |

### Build integrity

- **Lock files** (`packages.lock.json` with `RestorePackagesWithLockFile`, and `--locked-mode` in CI)
  make restore reproducible.
- **Package Source Mapping** in `nuget.config` ties each package prefix to one feed. It prevents
  *dependency confusion*: a public package with the same name as your internal one.
- **Central Package Management** (`Directory.Packages.props`) gives one place to see and patch versions.
- Base images: pin by digest or a specific tag; rebuild regularly for OS patches.

### S15: dead code from merge conflicts (MAJOR)

It is in the security rule list for a reason: orphaned methods, branches after `return`/`throw`, and
files like `*Old.cs` or `*Backup.cs` keep old, unreviewed logic in the binary. An old controller that
is still routed is an endpoint without anyone's attention. Delete it; Git keeps the history.

**At Smartcat:** the review skills tell the reviewer to read a repository's past-incidents file
(typically `.claude-review/past-incidents.md` or `policies/past-incidents.yaml`) if one exists, and to
cite the original MR or ticket when a finding matches one. This is how each repository keeps its own
bug history active in reviews.

---

## 13.14 How to test security properties

Security tests are normal tests that check a negative property: "this must **not** happen".

| Risk | Test idea | Level |
|---|---|---|
| Tenant isolation / IDOR | Seed two tenants; act as tenant A on tenant B's id; expect 404/403 and no write | Unit + integration |
| Missing `[Authorize]` | Architecture test: every controller action with `[HttpPost/Put/Delete/Patch]` has `[Authorize]` (or the controller has it) | Convention test |
| Every role | Parameterized test over all roles (`[TestCase(Role.Freelancer)]`, ...) with the expected result per role | Unit |
| Actor spoofing | Send a body with another `UserId`; assert the stored actor is the principal | Integration |
| Feature flag from body | Send the flag `true` in the body while the server flag is `false`; expect denial | Unit |
| NoSQL / regex injection | Input with quotes, `$ne`, `.*`, very long strings; expect exact-match behaviour or 400 | Unit |
| Path traversal | `../`, `%2e%2e/`, absolute paths, `\`; expect rejection | Unit (pure function) |
| SSRF | URLs to `127.0.0.1`, `169.254.169.254`, `[::1]`, a redirect to a private IP; expect rejection | Unit for `IsBlocked`, integration for the handler |
| Body limits | Request larger than the cap; expect 413, memory stays flat | Integration |
| JWT | Expired, wrong audience, wrong issuer, `alg: none`, token with `-`/`_` characters | Integration |
| Errors | Force an exception; assert the body has no stack trace and has a trace id | Integration |
| Config | Start the host with a missing secret; expect a startup failure | Integration |
| Antiforgery | POST without the token to a cookie-authenticated form endpoint; expect 400 | Integration |

```csharp
// Convention test: no write action without authorization metadata.
[Test]
public void Write_actions_should_require_authorization()
{
    var writeVerbs = new[] { typeof(HttpPostAttribute), typeof(HttpPutAttribute),
                             typeof(HttpDeleteAttribute), typeof(HttpPatchAttribute) };

    var offenders = typeof(ProjectsController).Assembly.GetTypes()
        .Where(t => typeof(ControllerBase).IsAssignableFrom(t) && !t.IsAbstract)
        .SelectMany(t => t.GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly)
            .Where(m => writeVerbs.Any(v => m.IsDefined(v, inherit: true)))
            .Where(m => !m.IsDefined(typeof(AuthorizeAttribute), true)
                     && !t.IsDefined(typeof(AuthorizeAttribute), true))
            .Select(m => $"{t.Name}.{m.Name}"))
        .ToList();

    Assert.That(offenders, Is.Empty);
}
```

This test only inspects attributes — structure, not private state — so it does not break the rule
against reflection into non-public members (see chapter 10, Unit and integration testing).

```csharp
// Path traversal: pure function, many cases, cheap.
[TestCase("../secrets.json")]
[TestCase("%2e%2e/secrets.json")]
[TestCase("a/../../b")]
[TestCase("a\\b")]
[TestCase("")]
public void Should_reject_unsafe_path(string raw)
{
    // Act
    var act = () => PathGuard.SafeRelativePath(raw);

    // Assert
    Assert.That(act, Throws.TypeOf<BadRequestException>());
}
```

Tip: a security fix without a test is a fix that the next refactoring can remove. In review, ask for
the negative test in the same MR.

---

## 13.15 Security in a code-review interview

Many interviews give you 50–150 lines and ask "review this". The interviewer watches your **order**
and your **priorities** more than your total number of findings.

### A fixed scan order

1. **Identity** — where does the user come from? `[Authorize]`? Actor from the principal or the body?
2. **Tenant** — every query and every id from the request: filtered or ownership-checked?
3. **Input → structure** — any string that becomes a query, path, command, URL, regex, type name?
4. **Output** — what goes back to the client? Exceptions, internal fields, other users' data?
5. **Secrets and crypto** — literals, weak algorithms, `Random`, disabled TLS?
6. **Logs and audit** — PII, tokens, bodies? Audit for high-value actions? Swallowed exceptions?
7. **Resources** — body size, unbounded loops or pages, timeouts, regex cost?

Then, and only then, style and naming. Say the order out loud; it shows a method.

### How to report a finding

Use the same shape as a real review comment: location, problem, impact, fix, severity.

> `ProjectsController.cs:42` — `GetById(id)` reads the project without an account filter. Any
> authenticated user can read any workspace's project by id (cross-tenant data leak). Add the
> `AccountId` from the user context to the filter, return 404 on mismatch, and add a two-tenant test.
> Critical / BLOCKER.

### Calibrate, do not inflate

- A missing tenant filter is Critical. `IConfiguration` in a service is MINOR. Do not put them in one
  list without severity — the interviewer wants to see that you know the difference.
- Say when you are unsure: "If this id is validated by a gateway before this service, this is a
  Warning; I would check that, not assume it."
- Know the exclusions: a weak hash in a test helper is not the same finding as in production code.

### A worked example

```csharp
[HttpPost("files/import")]
public async Task<IActionResult> Import([FromBody] ImportRequest request)
{
    try
    {
        _logger.LogInformation($"Import {request.Url} by {request.UserEmail}");
        var bytes = await _http.GetByteArrayAsync(request.Url);
        var path = Path.Combine("/data", request.WorkspaceId, request.FileName);
        await System.IO.File.WriteAllBytesAsync(path, bytes);
        if (request.Features.GetValue<bool>("IsAutoTranslateEnabled"))
            await _translator.StartAsync(request.WorkspaceId, path);
        return Ok();
    }
    catch (Exception ex) { return StatusCode(500, ex.ToString()); }
}
```

A strong answer, in priority order:

| # | Finding | Rule | Severity |
|---|---|---|---|
| 1 | No `[Authorize]` on a write endpoint | S20 / `missing-auth-endpoint` | Critical |
| 2 | `WorkspaceId` from the body, not compared with the authenticated workspace | S2 / `ownership-check` | Critical |
| 3 | `request.Url` fetched by the server without allow-list, redirects, IP checks | `ssrf-user-url` | Critical |
| 4 | `Path.Combine` with `WorkspaceId` and `FileName` from the body | `path-traversal` / S9 | Critical |
| 5 | Feature flag from the request body | S1 | BLOCKER |
| 6 | `ex.ToString()` in the response | `stack-trace-exposure` | Critical |
| 7 | Whole remote file loaded into memory, no size limit, no timeout or `CancellationToken` | S22 | MAJOR |
| 8 | Email (PII) and URL in an interpolated log message | `pii-in-logs`, `log-injection` | Warning |

Tip: when you find the first Critical, do not stop. Say "this alone blocks the MR" and continue — the
interviewer usually planted several.

---

## At Smartcat — summary of the company-specific points

- **Two review skills**: `security-smartcat-code-review` (OWASP 2021 checklist, Critical/Warning/
  Suggestion, exclusions, CI JSON status) and `review-security` (rules S1–S22 from real past findings in
  `smartcat-ai-agents`, BLOCKER/MAJOR/MINOR). The front-end companion is `review-frontend-security`
  (FS1–FS11).
- **Tenant identity** in `smartcat-ai-agents`: `src/Module.Mcp/Auth/PlatformUserContext.cs`, with a
  fail-closed `GetRequiredWorkspaceId()`.
- **Server-side feature flags**: `src/Module/Services/IFeatureService.cs`. Never decide access from
  `forwardedProps` / request body.
- **Hot zones** named by the review skill: the sidecar proxy
  (`src/Module/Agents/PdfTranslation/SidecarHttpProxy.cs`), the background-run entry point where
  HTTP-context state is snapshotted, and the client-tools middleware.
- **Calibration**: internal plain-HTTP API clients inside the cluster are not findings; TLS added and
  then disabled is.
- **Exclusions**: `test-workflows/**` skipped; tests and migrations downgraded Critical → Warning;
  examples/samples/mocks downgraded Warning → Suggestion.
- **Past incidents**: read `.claude-review/past-incidents.md` / `policies/past-incidents.yaml` when the
  repository has one, and cite the original MR in the finding.
- **Config layering**: secrets never in committed config; validate options at startup.

---

## Interview corner

### As the interviewee

**1. What is IDOR, and how do you prevent it in a multi-tenant .NET service?**
A strong answer covers:
- Direct object access by id without an authorization check on that object.
- Tenant filter in the query using the tenant from the authenticated context, not from the request.
- Ownership check after retrieval when the source cannot filter; scoped pre-check before unscoped APIs.
- 404 vs 403 choice; a two-tenant test.

**2. Why is a GUID id not a security control?**
A strong answer covers:
- Ids leak (URLs, logs, shares, screenshots); "hard to guess" is not "not allowed".
- Authorization must be explicit; GUIDs only reduce enumeration.

**3. How does NoSQL injection look in MongoDB with the C# driver?**
A strong answer covers:
- String-built `BsonDocument.Parse` filters, `$where`, operator objects from untyped client JSON,
  user-chosen field names, unescaped regex.
- Fix: typed `Builders<T>`, typed DTOs, allow-listed field names, `Regex.Escape` + anchor + length cap.

**4. What is wrong with `Path.Combine(root, userInput)`?**
A strong answer covers:
- `..` segments escape the root; an absolute second argument discards the root entirely.
- `Path.GetFullPath` + `StartsWith(root + separator, Ordinal)`, or `Path.GetFileName` only.
- For URLs: decode first, then check segments, then re-encode.

**5. Explain SSRF and how you would defend an "import from URL" feature.**
A strong answer covers:
- Server makes requests to attacker-chosen targets inside the network; metadata endpoint example.
- Allow-list, https only, no auto-redirect, check resolved IP at connect time (DNS rebinding),
  egress network policy, response size and time limits.

**6. PBKDF2 vs HKDF vs SHA-256 — when do you use which?**
A strong answer covers:
- SHA-256: fingerprints of non-secret data, not passwords or keys from passphrases.
- PBKDF2/Argon2id: low-entropy passwords, slow + salted.
- HKDF: derive several keys from an already strong key; `info` separates purposes.

**7. Why is `System.Random` wrong for a password-reset token?**
A strong answer covers:
- Predictable generator; `RandomNumberGenerator.GetBytes(32)`; Base64URL encoding; expiry and single use.

**8. What does a correct JWT validation configuration contain?**
A strong answer covers:
- Issuer, audience, lifetime, signing key validation; allowed algorithms; clock skew.
- `ReadJwtToken` does not validate; Base64URL vs Base64.

**9. When do you need antiforgery tokens?**
A strong answer covers:
- Cookie-based authentication (browser sends cookies automatically).
- Not needed in the same way for bearer tokens in a header; `SameSite` as a second layer.

**10. Why is `SetIsOriginAllowed(_ => true).AllowCredentials()` dangerous, and why is CORS not access control?**
A strong answer covers:
- Any website can make credentialed calls as the user and read the responses.
- CORS is enforced by browsers only; server-to-server calls ignore it.

**11. How do you handle secrets in an ASP.NET Core service?**
A strong answer covers:
- Platform-injected secrets, typed `IOptions<T>`, `ValidateOnStart`, no secrets in Git or front-end bundles.
- Rotation first when leaked; never log them.

**12. What should never be in logs, and what must always be?**
A strong answer covers:
- Never: tokens, passwords, PII, document content, response bodies at Information.
- Always: security failures, audit events for high-value operations with actor/tenant/target.

**13. How do you protect an endpoint from large request bodies?**
A strong answer covers:
- Per-route `RequestSizeLimit` / `IHttpMaxRequestBodySizeFeature`, 413, streaming instead of buffering.
- `ContentLength` may be missing; memory is shared across tenants on the pod.

**14. What is unsafe deserialization in .NET?**
A strong answer covers:
- `TypeNameHandling` not `None` on untrusted JSON; `BinaryFormatter` (removed in .NET 9).
- Allow-listed polymorphism with `[JsonDerivedType]` or a binder.

**15. How do you keep NuGet dependencies safe?**
A strong answer covers:
- NuGet Audit (transitive), failing CI on high severity, lock files, package source mapping,
  pinned exact versions, owned and documented pre-release/fork versions.

### As the interviewer

**What to ask.** Give a 40–80 line controller + service with 5–8 planted issues across categories
(like the worked example in 13.15). Ask for a review "as if it were a real MR", with severities.
Then ask one design question: "How would you build tenant isolation so a new developer cannot forget
it?"

**Depth probes:**

- "You said add the tenant filter. Where does the tenant id come from? Can a background job get it?"
- "Is 403 or 404 better here? Why?"
- "You check the URL host against an allow-list. The DNS answer changes after your check. What now?"
- "Why is `SHA256(password + salt)` still a bad password hash?"
- "The JWT parsing works in your tests. Why could it fail for 1 in 4 real users?" (Base64URL)
- "The feature flag is read from the body only for UI hints. When does it become a vulnerability?"
- "How would you test that no future endpoint is added without `[Authorize]`?"
- "We leaked an API key in a commit last week. What are the steps, in order?"

**Green flags:**

- Starts with identity and tenant, not with naming.
- Gives severity and impact for each finding, and separates blockers from hardening.
- Explains the "why" (attack and impact) in one sentence, without exploit theatre.
- Proposes a structural fix (fallback policy, repository that always adds the tenant, named
  `HttpClient` for user URLs, convention test), not only a line fix.
- Asks about context instead of assuming: "Is there a gateway check before this?"

**Red flags:**

- Lists only style issues or only "add try/catch".
- "It is internal, so it is safe" or "GUIDs cannot be guessed".
- Fixes injection with string escaping by hand instead of typed builders.
- Hashes passwords with SHA-256 or encrypts with a key from `SHA256(passphrase)`.
- Suggests `AllowAnyOrigin` or `DangerousAcceptAnyServerCertificateValidator` "for now".
- Logs the token "to debug the auth problem".

**Scoring rubric:**

| Level | Signals |
|---|---|
| Junior | Finds the stack trace and the hard-coded secret; knows "SQL injection"; no severity model |
| Senior | Finds IDOR/tenant, injection, SSRF and path traversal; correct fixes with typed APIs; rates severity; adds negative tests |
| Staff | All of Senior, plus: structural prevention (defaults, conventions, tests that fail on new code), threat model at trust boundaries, DNS rebinding and TOCTOU, key rotation and incident steps, calibrates false positives honestly |

---

## Exercises

1. **Find the tenant leak.** A repository has `UpdateStatusAsync(Guid taskId, Status status)` that
   calls `UpdateOneAsync(x => x.Id == taskId, ...)`. Rewrite it so it is safe, and write the test that
   would have caught the bug.
2. **Safe search.** Write a MongoDB filter for a "project name starts with" search box. Requirements:
   case-insensitive, tenant-scoped, safe against regex injection and ReDoS.
3. **Fix the sidecar path.** A proxy builds `"/" + conversationId + "/" + Uri.UnescapeDataString(file)`.
   List every problem (at least three) and write the fixed version.
4. **Key derivation review.** A colleague encrypts customer credentials with
   `Aes.Create()` and `Key = SHA256.HashData(Encoding.UTF8.GetBytes(_options.Passphrase))`, with a
   fixed IV. Write the review comment and the replacement design.
5. **SSRF design.** Design a webhook feature where customers register a URL that the service calls on
   events. What do you validate at registration, at call time, and at the network level?
6. **Threat model.** Run STRIDE on "an AI agent tool that reads a Drive file by id and sends its text
   to an LLM". Name the top three risks and their controls.

<details>
<summary>Answer notes</summary>

1. Add the tenant to the filter:
   `Builders<TaskItem>.Filter.Eq(x => x.AccountId, accountId) & Builders<TaskItem>.Filter.Eq(x => x.Id, taskId)`,
   with `accountId` from the user context (or passed explicitly from a trusted caller in a background
   job). Check `MatchedCount == 0` → not found. Test: seed a task for account B, act as account A,
   assert not found **and** that the stored status did not change.

2. Length cap (for example 100), `"^" + Regex.Escape(input)`, `BsonRegularExpression(pattern, "i")`,
   combined with `Eq(AccountId)`. Mention that a case-insensitive regex cannot use a normal index
   efficiently; a normalized lower-case field with a prefix regex, or a collation index, is better at
   scale.

3. Problems: no tenant/workspace in the path (S3); decoding **after** concatenation means `%2e%2e` or
   `%2f` becomes `..` or `/` — traversal (S9); no segment validation; no re-encoding. Fix: build from
   `workspaceId`, `conversationId`, `fileName`; for each, decode (if it arrives encoded), reject `.`,
   `..`, empty, `/`, `\`, then `Uri.EscapeDataString` and join.

4. Comment: S16 MAJOR — fast unsalted hash as KDF; fixed IV with CBC leaks equal plaintexts and has no
   integrity. Replacement: a random master key from the secret store (not a passphrase), HKDF per
   purpose, `AesGcm` with a random 12-byte nonce per message, store `{keyId, nonce, tag, ciphertext}`,
   options validated at startup (S17), documented rotation. If a passphrase is unavoidable, PBKDF2 with
   a per-key salt and high iterations.

5. Registration: parse with `Uri`, https only, reject IP literals in private ranges and user info,
   optionally verify ownership (challenge). Call time: named `HttpClient` with `ConnectCallback` IP
   check, `AllowAutoRedirect = false`, short timeouts, response size cap, sign the payload with HMAC
   so the receiver can verify it. Network: egress policy that blocks internal ranges and the metadata
   endpoint for that workload.

6. Example: (I) cross-tenant read — file id not checked against the workspace → ownership check
   after retrieval (S2); (T/E) prompt injection in the file text makes the agent call other tools →
   treat file text as data, limit tool permissions, require confirmation for writes; (I) PII/document
   text in logs or traces → log ids only (S11). Also D: very large files → size cap before sending.

</details>

---

## Summary

- Tenant isolation is the number one risk in a multi-tenant SaaS: filter by the tenant from the
  authenticated context, check ownership, and test with two tenants.
- Identity comes from the principal, never from the request body — this includes actor ids and
  feature flags.
- Injection is data becoming structure: use typed MongoDB builders, `ArgumentList`, allow-listed field
  names, escaped and anchored regex, and never `$where` or `TypeNameHandling` on untrusted input.
- `Path.Combine` drops the root for absolute paths; resolve with `GetFullPath` and check the prefix;
  for URLs, decode first, then validate segments, then re-encode.
- SSRF needs layers: allow-list, no auto-redirect, IP check at connect time, egress rules.
- Right crypto for the job: PBKDF2/Argon2id for passwords, HKDF for strong keys, `AesGcm` for
  encryption, `RandomNumberGenerator` for tokens, never disabled TLS validation.
- Validate JWTs fully (issuer, audience, lifetime, key, algorithms); JWT parts are Base64URL.
- Never return stack traces; use ProblemDetails with a trace id. Limit request bodies and stream.
- Secrets: platform-injected, typed `IOptions<T>`, `ValidateOnStart`, rotate first when leaked.
- In a review, follow a fixed order (identity, tenant, input, output, secrets, logs, resources) and
  give every finding a severity and a fix.

Anki deck: anki/13-security.txt

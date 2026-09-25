export const meta = {
  name: 'norway-batch',
  description: 'Produce one reviewed and adjudicated contract-driven Norway batch patch without applying or committing it; the full verification ladder runs once, at apply time',
  whenToUse: 'Run uv run python scripts/norway_batch_preflight.py <contract> --json > /tmp/facts.json first, then invoke with args {mode, factsPath} pointing at that file. Do NOT paste the facts inline: transcribing several KB of JSON is the least reliable step here and caused three Load-phase aborts on 2026-07-31. {mode, facts} still works when the object is passed programmatically. Invoke by scriptPath, not by name: name resolution serves a script cached at session start.',
  phases: [
    {title: 'Preflight', detail: 'judge the contract assumptions that need code read, not facts computed'},
    {title: 'Implement', detail: 'produce the smallest contract-compliant patch in isolation'},
    {title: 'Review', detail: 'review correctness and architecture independently'},
    {title: 'Adjudicate', detail: 'confirm only evidence-backed reviewer findings'},
    {title: 'Fix', detail: 'apply confirmed in-scope corrections in fresh isolation'},
    {title: 'Report', detail: 'return the patch, its apply ladder, and the proposed progress update without merging'},
  ],
}

// Ported from read-aloud-2's typescript-batch workflow (its battle scars are kept as comments
// where they still bind). LawVM deltas: uv-run toolchain, LAWVM_CANONICAL_DATA_ROOT corpus
// resolution in isolated worktrees, ./scripts/ci.sh --affected as the apply-time ladder, and
// review foci drawn from AGENTS.md (typed receipts, fail-loud, compare-only lane discipline).
const WORKFLOW = 'norway-batch'
const NOT_RUN_EXIT_CODE = -1
const SHA256_PATTERN = /^[0-9a-f]{64}$/
const STRING_ARRAY = {type: 'array', items: {type: 'string'}}

const STAGE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['id', 'command', 'status', 'exitCode', 'output'],
  properties: {
    id: {type: 'string'},
    command: {type: 'string'},
    status: {type: 'string', enum: ['passed', 'failed', 'not-run']},
    exitCode: {type: 'integer'},
    output: {type: 'string'},
  },
}

const CONTRACT_CHECK_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['index', 'check', 'passed', 'evidence'],
  properties: {
    index: {type: 'integer'},
    check: {type: 'string'},
    passed: {type: 'boolean'},
    evidence: {type: 'string'},
  },
}

// Only the contract's prose assumptions remain: everything computable is supplied as facts.
const PREFLIGHT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['contractChecks', 'summary'],
  properties: {
    contractChecks: {type: 'array', items: CONTRACT_CHECK_SCHEMA},
    summary: {type: 'string'},
  },
}

const PATCH_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: [
    'status', 'baseHead', 'patchText', 'patchSha256', 'patchBytes', 'artifactPath',
    'artifactPersisted', 'changedFiles', 'addedFiles', 'modifiedFiles', 'deletedFiles',
    'diffCheckPassed', 'scopePassed', 'cleanupSucceeded', 'stages', 'notes',
  ],
  properties: {
    status: {type: 'string', enum: ['ready', 'abort']},
    baseHead: {type: 'string'},
    patchText: {type: 'string'},
    patchSha256: {type: 'string'},
    patchBytes: {type: 'integer'},
    artifactPath: {type: 'string'},
    artifactPersisted: {type: 'boolean'},
    changedFiles: STRING_ARRAY,
    addedFiles: STRING_ARRAY,
    modifiedFiles: STRING_ARRAY,
    deletedFiles: STRING_ARRAY,
    diffCheckPassed: {type: 'boolean'},
    scopePassed: {type: 'boolean'},
    cleanupSucceeded: {type: 'boolean'},
    stages: {type: 'array', items: STAGE_SCHEMA},
    notes: STRING_ARRAY,
  },
}

const FINDING_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: [
    'id', 'severity', 'confidence', 'file', 'line', 'claim', 'evidence',
    'failureScenario', 'requiredFix', 'insideContract',
  ],
  properties: {
    id: {type: 'string'},
    severity: {type: 'string', enum: ['high', 'medium', 'low']},
    confidence: {type: 'string', enum: ['high', 'medium', 'low']},
    file: {type: 'string'},
    line: {type: 'integer'},
    claim: {type: 'string'},
    evidence: {type: 'string'},
    failureScenario: {type: 'string'},
    requiredFix: {type: 'string'},
    insideContract: {type: 'boolean'},
  },
}

const REVIEW_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['status', 'kind', 'baseHeadMatches', 'patchPathsValid', 'verdict', 'findings', 'summary'],
  properties: {
    status: {type: 'string', enum: ['completed', 'unable']},
    kind: {type: 'string', enum: ['correctness', 'architecture']},
    baseHeadMatches: {type: 'boolean'},
    patchPathsValid: {type: 'boolean'},
    verdict: {type: 'string', enum: ['approve', 'findings', 'unable']},
    findings: {type: 'array', items: FINDING_SCHEMA},
    summary: {type: 'string'},
  },
}

const CONFIRMED_FINDING_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['sourceFindingIds', 'claim', 'evidence', 'requiredFix', 'insideContract', 'blocksPatch'],
  properties: {
    sourceFindingIds: STRING_ARRAY,
    claim: {type: 'string'},
    evidence: {type: 'string'},
    requiredFix: {type: 'string'},
    insideContract: {type: 'boolean'},
    // Whether the patch itself is wrong. A defect the patch introduces blocks it; residue the
    // patch merely reveals in a file outside the contract does not. Conflating the two threw
    // away a sound patch and 33 minutes of work in the source repo.
    blocksPatch: {type: 'boolean'},
  },
}

const REJECTED_FINDING_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['id', 'reason'],
  properties: {
    id: {type: 'string'},
    reason: {type: 'string'},
  },
}

const ADJUDICATION_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['status', 'confirmedFindings', 'rejectedFindings', 'needsFixer', 'summary'],
  properties: {
    status: {type: 'string', enum: ['completed', 'unable']},
    confirmedFindings: {type: 'array', items: CONFIRMED_FINDING_SCHEMA},
    rejectedFindings: {type: 'array', items: REJECTED_FINDING_SCHEMA},
    needsFixer: {type: 'boolean'},
    summary: {type: 'string'},
  },
}

function normalizeRepoPath(value, repositoryRoot = '') {
  let path = String(value || '').trim()
  const root = repositoryRoot ? `${repositoryRoot.replace(/\/$/, '')}/` : ''
  if (root && path.startsWith(root)) path = path.slice(root.length)
  path = path.replace(/^\.\//, '')
  return path
}

function sorted(values) {
  return [...values].sort()
}

function sameStrings(left, right) {
  const a = sorted(left)
  const b = sorted(right)
  return a.length === b.length && a.every((value, index) => value === b[index])
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function unique(values) {
  return [...new Set(values)]
}

function isSafeRepoPath(path) {
  return typeof path === 'string'
    && path.length > 0
    && !path.startsWith('/')
    && !path.startsWith('./')
    && !path.split('/').includes('..')
    && !/[\x00-\x1f\x7f]/.test(path)
    && !/\s/.test(path)
    && !path.startsWith('"')
}

function utf8ByteLength(value) {
  let bytes = 0
  for (const character of String(value)) {
    const codePoint = character.codePointAt(0)
    if (codePoint <= 0x7f) bytes += 1
    else if (codePoint <= 0x7ff) bytes += 2
    else if (codePoint <= 0xffff) bytes += 3
    else bytes += 4
  }
  return bytes
}

function inspectPatch(patchText) {
  const paths = []
  const added = []
  const deleted = []
  const invalidHeaders = []
  const forbiddenExtendedHeaders = []
  let current = ''
  for (const line of String(patchText || '').split('\n')) {
    const match = /^diff --git a\/([^\t\n]+) b\/([^\t\n]+)$/.exec(line)
    if (line.startsWith('diff --git ')) {
      if (!match) {
        invalidHeaders.push(line)
        current = ''
        continue
      }
      const source = match[1]
      const target = match[2]
      current = target
      if (!isSafeRepoPath(source) || !isSafeRepoPath(target) || source !== target) invalidHeaders.push(line)
      paths.push(target)
    } else if (/^(rename|copy) (from|to) /.test(line)) {
      forbiddenExtendedHeaders.push(line)
    } else if (line.startsWith('--- ') || line.startsWith('+++ ')) {
      if (!current) {
        invalidHeaders.push(line)
      } else {
        const expectedPrefix = line.startsWith('--- ') ? 'a/' : 'b/'
        const headerPath = line.slice(4)
        if (headerPath !== '/dev/null' && headerPath !== `${expectedPrefix}${current}`) invalidHeaders.push(line)
      }
    } else if (current && line.startsWith('new file mode ')) {
      added.push(current)
    } else if (current && line.startsWith('deleted file mode ')) {
      deleted.push(current)
    }
  }
  const changed = unique(paths)
  const addedSet = new Set(added)
  const deletedSet = new Set(deleted)
  const modified = changed.filter(path => !addedSet.has(path) && !deletedSet.has(path))
  return {
    paths: changed,
    added: unique(added),
    modified,
    deleted: unique(deleted),
    invalidHeaders,
    forbiddenExtendedHeaders,
  }
}

function validateStageSequence(stages, specs, requireAllPassed) {
  const reasons = []
  if (!Array.isArray(stages) || stages.length !== specs.length) {
    reasons.push(`Expected ${specs.length} recorded stages, received ${Array.isArray(stages) ? stages.length : 'non-array'}`)
    return reasons
  }
  let stopped = false
  for (let index = 0; index < specs.length; index++) {
    const stage = stages[index]
    const spec = specs[index]
    if (stage.id !== spec.id || stage.command !== spec.command) {
      reasons.push(`Stage ${index + 1} does not match frozen command ${spec.id}`)
    }
    if (stage.status === 'passed' && stage.exitCode !== 0) reasons.push(`${stage.id}: passed stage has nonzero exit code`)
    if (stage.status === 'failed' && (stage.exitCode === 0 || stage.exitCode === NOT_RUN_EXIT_CODE)) reasons.push(`${stage.id}: failed stage has invalid exit code`)
    if (stage.status === 'not-run' && stage.exitCode !== NOT_RUN_EXIT_CODE) reasons.push(`${stage.id}: not-run stage must use exit code ${NOT_RUN_EXIT_CODE}`)
    if (stopped && stage.status !== 'not-run') reasons.push(`${stage.id}: stage ran after fail-fast stop`)
    if (!stopped && stage.status === 'failed') stopped = true
    if (!stopped && stage.status === 'not-run') {
      reasons.push(`${stage.id}: stage was skipped before a failure`)
      stopped = true
    }
    if (requireAllPassed && stage.status !== 'passed') reasons.push(`${stage.id}: required stage did not pass`)
  }
  return reasons
}

// The boundary is enforced; the manifest is observed. A patch that stays inside the boundary but
// touches something the contract did not list is reported to the reviewers rather than discarded,
// because a path list cannot tell scope creep from a deletion that obviously orphaned a module.
function scopeDeviations(patchInfo, scopeMatchers, contract) {
  const listed = path => scopeMatchers.allowed.some(matcher => matcher.test(path))
  const required = new Set([
    ...contract.scope.requiredChangedPaths,
    ...contract.scope.requiredAddedPaths,
    ...contract.scope.requiredDeletedPaths,
  ])
  const deviations = []
  for (const path of patchInfo.paths) if (!listed(path)) deviations.push(`touched ${path}, which the contract does not list`)
  for (const path of patchInfo.added) if (!required.has(path)) deviations.push(`added ${path}, which the contract does not require`)
  for (const path of patchInfo.deleted) if (!required.has(path)) deviations.push(`deleted ${path}, which the contract does not require`)
  return unique(deviations)
}

function validatePatchResult(result, contract, runHead, targetedSpecs, scopeMatchers) {
  const reasons = []
  if (!result) return ['Patch-producing agent returned no result']
  const patchInfo = inspectPatch(result.patchText)
  const expectedRequired = unique([
    ...contract.scope.requiredChangedPaths,
    ...contract.scope.requiredAddedPaths,
    ...contract.scope.requiredDeletedPaths,
  ])
  if (result.status !== 'ready') reasons.push('Patch-producing agent aborted')
  if (result.baseHead !== runHead) reasons.push('Patch-producing agent used the wrong base HEAD')
  if (!result.patchText || !SHA256_PATTERN.test(result.patchSha256) || result.patchBytes <= 0) reasons.push('Patch text, SHA-256, or byte size is missing or malformed')
  // The durable artifact is the patch's identity: the JSON transport is not byte-faithful, so the
  // file the producing agent wrote and re-hashed is what the human applies.
  if (!result.artifactPersisted || result.artifactPath !== `/tmp/lawvm-norway-batches/${contract.id}/${result.patchSha256}.patch`) {
    reasons.push('Durable patch artifact was not persisted at its canonical path')
  }
  // patchText is NOT byte-faithful: the JSON transport can unescape sequences one time too many.
  // The artifact and its SHA-256 are the identity; the human re-hashes the file at apply time. A
  // mismatch is logged because it tells reviewers the text they read differs from the patch that
  // will be applied.
  if (result.patchBytes !== utf8ByteLength(result.patchText)) {
    log(`Transport note: patchText measures ${utf8ByteLength(result.patchText)} bytes but the patch is ${result.patchBytes}. `
      + `Escape sequences were unescaped in transit; the artifact and its SHA-256 remain authoritative.`)
  }
  if (patchInfo.invalidHeaders.length || patchInfo.forbiddenExtendedHeaders.length) reasons.push('Patch contains an unsafe, renamed, copied, or mismatched path header')
  const outsideBoundary = patchInfo.paths.filter(path => !scopeMatchers.boundary.some(matcher => matcher.test(path)))
  if (outsideBoundary.length) reasons.push(`Patch crosses the contract scope boundary: ${outsideBoundary.join(', ')}`)
  if (!contract.scope.requiredChangedPaths.every(path => patchInfo.modified.includes(path))) reasons.push('Patch omits or misclassifies a required changed path')
  if (!contract.scope.requiredAddedPaths.every(path => patchInfo.added.includes(path))) reasons.push('Patch omits a required added path')
  if (!contract.scope.requiredDeletedPaths.every(path => patchInfo.deleted.includes(path))) reasons.push('Patch omits a required deleted path')
  if (!expectedRequired.every(path => patchInfo.paths.includes(path))) reasons.push('Patch omits a required path')
  if (!sameStrings(result.changedFiles.map(path => normalizeRepoPath(path)), patchInfo.paths)) reasons.push('Reported changed files do not match patch headers')
  if (!sameStrings(result.addedFiles.map(path => normalizeRepoPath(path)), patchInfo.added)) reasons.push('Reported added files do not match patch headers')
  if (!sameStrings(result.modifiedFiles.map(path => normalizeRepoPath(path)), patchInfo.modified)) reasons.push('Reported modified files do not match patch headers')
  if (!sameStrings(result.deletedFiles.map(path => normalizeRepoPath(path)), patchInfo.deleted)) reasons.push('Reported deleted files do not match patch headers')
  // diffCheckPassed is work only the agent can do (git diff --check). scopePassed is its opinion
  // about scope, which this function has already decided for itself from the boundary matchers —
  // and an in-boundary path off the manifest is a deviation for the reviewers, not an abort.
  if (!result.diffCheckPassed) reasons.push('Patch diff validation failed')
  if (!result.cleanupSucceeded) reasons.push('Patch-producing agent did not clean its isolated worktree')
  // An implementer that also ran extra stages has over-delivered, not failed. Validate the frozen
  // targeted sequence, and among surplus stages fail only on a real failure so a hidden one cannot
  // ride along. A surplus stage reported not-run carries no failure information.
  const targetedIds = new Set(targetedSpecs.map(spec => spec.id))
  const stages = Array.isArray(result.stages) ? result.stages : []
  reasons.push(...validateStageSequence(stages.filter(stage => targetedIds.has(stage.id)), targetedSpecs, true))
  for (const stage of stages) {
    if (!targetedIds.has(stage.id) && stage.status === 'failed') reasons.push(`${stage.id}: extra stage the implementer ran failed`)
  }
  return reasons
}

// Reviewers run in parallel and cannot coordinate an id namespace, so both reach for F1. Namespace
// ids by reviewer kind rather than discarding a finished run over the collision. The verdict is
// bookkeeping too: the findings are the substance, and whether any of them blocks is the
// adjudicator's call, so let the label follow the findings instead of contradicting them.
function normalizeReviews(reviews) {
  return reviews.map(review => {
    if (!review || !Array.isArray(review.findings)) return review
    const findings = review.findings.map(finding => ({...finding, id: `${review.kind}:${finding.id}`}))
    return {...review, findings, verdict: review.verdict === 'unable' ? 'unable' : (findings.length ? 'findings' : 'approve')}
  })
}

function validateReviews(reviews) {
  const reasons = []
  const ids = []
  for (const review of reviews) {
    const findingCount = review.findings.length
    if (review.verdict === 'approve' && findingCount !== 0) reasons.push(`${review.kind}: approve verdict contains findings`)
    if (review.verdict === 'findings' && findingCount === 0) reasons.push(`${review.kind}: findings verdict has no findings`)
    ids.push(...review.findings.map(finding => finding.id))
  }
  if (unique(ids).length !== ids.length) reasons.push('Reviewer finding IDs are not globally unique')
  return reasons
}

// A rejected finding survives only in a session-scoped journal unless the report carries it, so
// join the adjudicator's reason back to the reviewer's claim and keep both.
function resolveRejected(reviews, adjudication) {
  const byId = new Map(reviews.flatMap(review => review.findings.map(finding => [finding.id, finding])))
  return (adjudication.rejectedFindings || []).map(rejected => {
    const finding = byId.get(rejected.id)
    return {
      id: rejected.id,
      reason: rejected.reason,
      severity: finding?.severity || '',
      file: finding?.file || '',
      line: finding?.line ?? 0,
      claim: finding?.claim || '(claim not found in the reviews)',
      requiredFix: finding?.requiredFix || '',
    }
  })
}

function validateAdjudicationPartition(reviews, adjudication) {
  const reasons = []
  const reviewIds = reviews.flatMap(review => review.findings.map(finding => finding.id))
  const confirmedIds = adjudication.confirmedFindings.flatMap(finding => finding.sourceFindingIds)
  const rejectedIds = adjudication.rejectedFindings.map(finding => finding.id)
  if (unique(confirmedIds).length !== confirmedIds.length) reasons.push('Adjudication confirms a reviewer finding more than once')
  if (unique(rejectedIds).length !== rejectedIds.length) reasons.push('Adjudication rejects a reviewer finding more than once')
  if (confirmedIds.some(id => rejectedIds.includes(id))) reasons.push('Adjudication both confirms and rejects the same finding')
  if (!sameStrings([...confirmedIds, ...rejectedIds], reviewIds)) reasons.push('Adjudication does not partition every reviewer finding exactly once')
  return reasons
}

// The fixer acts on defects inside the contract. Residue outside it is reported, not fixed.
function fixableFindings(adjudication) {
  return (adjudication.confirmedFindings || []).filter(finding => finding.insideContract)
}

// Confirmed, real, and someone else's problem. This is the only durable record of it, so it is
// collected across every adjudication in the run and deduplicated by claim.
function resolveResidue(adjudications) {
  const byClaim = new Map()
  for (const adjudication of adjudications) {
    for (const finding of (adjudication?.confirmedFindings || [])) {
      if (finding.insideContract || byClaim.has(finding.claim)) continue
      byClaim.set(finding.claim, {claim: finding.claim, evidence: finding.evidence, requiredFix: finding.requiredFix})
    }
  }
  return [...byClaim.values()]
}

function compactStages(stages) {
  return (stages || []).map(stage => ({
    id: stage.id,
    command: stage.command,
    status: stage.status,
    exitCode: stage.exitCode,
    output: stage.output,
  }))
}

function compactReviews(reviews) {
  return (reviews || []).map(review => ({
    kind: review.kind,
    status: review.status,
    verdict: review.verdict,
    baseHeadMatches: review.baseHeadMatches,
    patchPathsValid: review.patchPathsValid,
    findings: review.findings,
    summary: review.summary,
  }))
}

function emptyReport(status, reasons, context = {}) {
  return {
    reportVersion: 1,
    workflow: WORKFLOW,
    batchId: context.contract?.id || '',
    status,
    merged: false,
    phase: context.phase || 'Load',
    base: {
      branch: context.contract?.branch || context.facts?.branch || '',
      productBaseline: context.facts?.productBaseline || '',
      runHead: context.facts?.head || '',
    },
    inputs: context.facts ? {
      contractPath: context.facts.contractPath || '',
      contractSha256: context.facts.contractSha256,
      progressSha256: context.facts.progressSha256,
      sourceReviewSha256: context.facts.sourceReviewSha256,
      workflowSha256: context.facts.workflowSha256,
    } : null,
    preflight: context.facts ? {
      committedDriftPaths: context.facts.committedDriftPaths,
      dirtyPaths: context.facts.dirtyPaths,
      failedContractChecks: (context.preflight?.contractChecks || []).filter(item => !item.passed),
      summary: context.preflight?.summary || '',
    } : null,
    patch: null,
    reviews: compactReviews(context.reviews),
    adjudication: context.adjudication || null,
    fieldVerification: context.contract?.fieldVerification || null,
    suggestedProgressStatus: status,
    abortReasons: reasons,
    summary: reasons.join('; ') || status,
  }
}

// The calling session runs scripts/norway_batch_preflight.py and passes its --json output straight
// in, so every git, ledger and scope fact arrives already established. Nothing here has to
// interrogate an agent about the repository, and nothing has to cross-examine what an agent says
// it saw. The tool may deliver args as an object or as a JSON string, and the runtime's own
// resume-from-run-id line reproduces them stringified, so accept both.
// PREFER {mode, factsPath}. Pasting the whole preflight --json blob inline means a human or a
// model retypes several KB of JSON per attempt, and that transcription is the single least
// reliable step in this workflow: on 2026-07-31 it produced three consecutive Load-phase aborts
// (at 16.7 KB, 14.0 KB and 11.1 KB) plus one fabricated sha256. Size is NOT the cause — a 13.1 KB
// envelope ran fine and an 11.1 KB one failed. Hand-copying is. Pass the PATH instead; the Load
// agent reads the file, so the bytes never pass through a keyboard.
function readArgs(value) {
  if (isPlainObject(value)) return {args: value, transport: null}
  if (typeof value !== 'string') return {args: {}, transport: `args arrived as ${typeof value}, not an object or JSON string`}
  if (!value.trim().startsWith('{')) return {args: {}, transport: `args string does not begin with '{' (${value.length} bytes)`}
  try {
    const parsed = JSON.parse(value)
    if (!isPlainObject(parsed)) return {args: {}, transport: `args JSON parsed to ${typeof parsed}, not an object`}
    return {args: parsed, transport: null}
  } catch (err) {
    return {args: {}, transport: [
      `args JSON.parse failed after ${value.length} bytes: ${String(err).slice(0, 160)}.`,
      value.trimEnd().endsWith('}')
        ? 'The string is terminated, so it was corrupted in transcription rather than truncated.'
        : 'The string does not end in "}", so it was cut short.',
      'Do not retype the envelope. Re-invoke with the small form instead:',
      'args {"mode":"full","factsPath":"<path to the preflight --json output>"}.',
    ].join(' ')}
  }
}
const {args: parsedArgs, transport: transportFault} = readArgs(args)
const inputMode = parsedArgs.mode || 'full'
let facts = isPlainObject(parsedArgs.facts) ? parsedArgs.facts : null

// factsPath: read the preflight output off disk instead of trusting a transcribed blob. One
// agent, one cat, no interpretation — it is told to return the bytes and nothing else.
if (!facts && typeof parsedArgs.factsPath === 'string' && parsedArgs.factsPath.trim()) {
  const factsPath = parsedArgs.factsPath.trim()
  log(`Reading preflight facts from ${factsPath}.`)
  const raw = await agent(
    `Run exactly: cat ${factsPath}\n\n` +
    'Return the file contents verbatim as your entire final message: raw JSON, nothing else. ' +
    'No markdown fence, no commentary, no summary, no reformatting, no key reordering. ' +
    'If the file does not exist or is empty, return exactly: MISSING',
    {label: 'load:facts', phase: 'Load', effort: 'low', agentType: 'Explore'},
  )
  const text = typeof raw === 'string' ? raw.trim() : ''
  const body = text.startsWith('```')
    ? text.replace(/^```[a-zA-Z]*\n?/, '').replace(/```$/, '').trim()
    : text
  if (!body || body === 'MISSING') {
    return emptyReport('aborted', [
      `Could not read preflight facts from ${factsPath}.`,
      'Regenerate them: uv run python scripts/norway_batch_preflight.py <contract-path> --json > <path>',
    ], {phase: 'Load'})
  }
  try {
    const loaded = JSON.parse(body)
    facts = isPlainObject(loaded) ? loaded : null
  } catch (err) {
    return emptyReport('aborted', [
      `Preflight facts at ${factsPath} did not parse as JSON: ${String(err).slice(0, 200)}`,
      `The agent returned ${body.length} bytes beginning: ${body.slice(0, 120)}`,
    ], {phase: 'Load'})
  }
  if (!facts) {
    return emptyReport('aborted', [`Preflight facts at ${factsPath} are not a JSON object.`], {phase: 'Load'})
  }
}

if (!facts) {
  return emptyReport('aborted', [
    transportFault
      ? `Preflight facts did not survive transport: ${transportFault}`
      : 'No preflight facts were supplied.',
    'Run: uv run python scripts/norway_batch_preflight.py <contract-path> --json',
    'then invoke this workflow with args {mode, facts} where facts is that output.',
  ], {phase: 'Load'})
}
if (!['full', 'preflight-only'].includes(inputMode)) {
  return emptyReport('aborted', [`Unsupported mode: ${String(inputMode)}`], {phase: 'Load', facts})
}

const contract = facts.contract
const contractPath = facts.contractPath || ''
if (!facts.runnable || facts.errors.length || facts.readiness.length) {
  return emptyReport('aborted', ['Supplied preflight facts do not authorise a run', ...facts.errors, ...facts.readiness], {phase: 'Load', facts, contract, contractPath})
}
const missingFacts = ['head', 'branch', 'repositoryRoot', 'productBaseline', 'contractSha256']
  .filter(key => typeof facts[key] !== 'string' || !facts[key])
if (!isPlainObject(contract) || !isPlainObject(contract.verification) || missingFacts.length) {
  return emptyReport('aborted', [`Preflight facts are incomplete: ${missingFacts.join(', ') || 'contract is missing or malformed'}`], {phase: 'Load', facts})
}

const targetedSpecs = contract.verification.targeted
const fullSpecs = contract.verification.full
// fullSpecs is the apply-time ladder (./scripts/ci.sh --affected over the contract scope). It is
// not run by any agent here: the whole ladder runs exactly once, at apply time, in the main
// checkout, where a failure is reversible with git apply -R on a clean committed tree. Targeted
// stages keep earning their place in Implement and Fix as the fast feedback loop.
const scopeMatchers = {
  boundary: (facts.scopePatterns?.boundary || []).map(source => new RegExp(source)),
  allowed: (facts.scopePatterns?.allowed || []).map(source => new RegExp(source)),
}
if (!scopeMatchers.boundary.length) {
  return emptyReport('aborted', ['Preflight facts carry no scope boundary'], {phase: 'Load', facts, contract, contractPath})
}
const frozenContract = JSON.stringify(contract)

// Isolated worktrees do not carry the gitignored corpus archives. TWO exports are needed and
// they are not interchangeable: lawvm.corpus_store honors LAWVM_CANONICAL_DATA_ROOT, but Norway
// source resolution (norway/sources.resolve_no_source_path) reads only LAWVM_NORWAY_DB /
// LAWVM_NORWAY_DATA_DIR and otherwise falls back to the worktree's own absent data/ dir. Missing
// the second one makes every Norway replay fail with "no original-act source available", which
// reads like a data gap rather than a missing variable. Measured on the W-2 spike.
const corpusEnvLine = `export LAWVM_CANONICAL_DATA_ROOT=${facts.repositoryRoot} `
  + `LAWVM_NORWAY_DB=${facts.repositoryRoot}/data/norway.farchive`

phase('Preflight')
log('Judging the contract assumptions that need code read, not facts computed.')
const preflight = await agent(`
Judge one frozen contract's stated assumptions against the code in ${facts.repositoryRoot}.
Read only. Do not edit, build, package, install, create files, commit, stage, stash, reset, rebase, or push.

Every git, ledger, scope and prerequisite fact for this batch has already been established
deterministically by scripts/norway_batch_preflight.py. Do not re-derive them. Your only job is the
contract's preflightChecks, which need code to be read and judged rather than computed.

Run Python entry points through uv (uv run lawvm ..., uv run python ...) — bare python is the
wrong interpreter in this repository. Read-only lawvm CLI commands (no-divergence, no-verify) are
allowed when a check cites their output.

Frozen contract:
${frozenContract}

Evaluate every preflightChecks entry independently and return one record per entry. Set index to
its zero-based position in contract.preflightChecks, restate the check in your own words, and give
passed true or false with concise concrete evidence. If a check cannot be proven from repository
evidence, return passed false rather than assuming it. Judge only what each check actually claims.
`, {label: `preflight:${contract.id}`, phase: 'Preflight', effort: 'high', agentType: 'Explore', schema: PREFLIGHT_SCHEMA})

const preflightReasons = []
if (!preflight) preflightReasons.push('Preflight returned no result')
if (preflight) {
  const checkIndexes = preflight.contractChecks.map(item => item.index)
  const expectedIndexes = contract.preflightChecks.map((_, index) => index)
  if (unique(checkIndexes).length !== checkIndexes.length || !sameStrings(checkIndexes.map(String), expectedIndexes.map(String))) {
    preflightReasons.push('Preflight did not evaluate the exact contract check set')
  }
  for (const check of preflight.contractChecks) {
    if (!check.passed) preflightReasons.push(`Contract preflight failed: ${contract.preflightChecks[check.index] ?? `check ${check.index}`}`)
  }
}

if (preflightReasons.length) {
  return emptyReport('aborted', preflightReasons, {phase: 'Preflight', facts, contract, contractPath, preflight})
}
if (inputMode === 'preflight-only') {
  const result = emptyReport('preflight-passed', [], {phase: 'Preflight', facts, contract, contractPath, preflight})
  result.suggestedProgressStatus = 'ready'
  result.summary = 'Supplied facts and the contract assumptions both hold; no write-capable agent was started.'
  return result
}

phase('Implement')
log(`Producing the smallest compliant ${contract.id} patch in an isolated worktree.`)
const implementation = await agent(`
Implement the frozen Norway batch in an isolated worktree. Do not touch the user's main worktree.
Do not commit, stage, stash, reset, rebase, push, weaken tests, or edit outside the contract.

Initial HEAD must equal ${facts.head}; abort before edits if it does not.
Frozen contract:
${frozenContract}

Path rules (two levels — the boundary is the limit, the manifest is the expectation):
- Scope boundary, never cross it: ${contract.scope.boundary?.length ? contract.scope.boundary.join(', ') : contract.scope.allowedPaths.join(', ')}
- Allowed paths, the manifest of what this contract expects to change: ${contract.scope.allowedPaths.join(', ')}
- A path inside the boundary but off the manifest is a DEVIATION, not a violation: change it when the work genuinely requires it, report it in notes, and keep scopePassed true. Reserve scopePassed false for a path outside the boundary.
- Existing paths that must change: ${contract.scope.requiredChangedPaths.join(', ') || '(none)'}
- Paths that must be added: ${contract.scope.requiredAddedPaths.join(', ') || '(none)'}
- Paths that must be deleted: ${contract.scope.requiredDeletedPaths.join(', ') || '(none)'}
- No other addition or deletion is allowed.

Implementation rules (this is LawVM — AGENTS.md conventions bind):
- Satisfy the objective and requirements while preserving every invariant.
- Respect all exclusions and stop conditions. Abort rather than broadening scope or improvising around a changed assumption.
- Fail loud: no silent fallback, no swallowed exception, no untyped skip. New behavior that filters, recovers, or projects must emit its typed receipt/adjudication/projection like the surrounding code does.
- The compare-only verification lane never mutates replay-authoritative state.
- Add no stub, wrapper, compatibility layer, framework, migration, or abstraction unless the contract explicitly requires it.
- Treat the urge to explain yourself as evidence of a defect: if you find yourself writing a paragraph-long comment defending a workaround, the implementation is wrong. Stop and abort instead.
- Match surrounding code style and comment density.

Verification and cleanup:
1. First run ${corpusEnvLine} so the gitignored corpus archives resolve from the isolated worktree, and invoke every Python entry point through uv (uv run pytest, uv run ruff, uv run lawvm, ...) — uv syncs the worktree environment on first use; bare python bypasses the locked env.
2. Run exactly the targeted commands below, in order, and fail fast. Return one stage record for every command; after a failure mark every remaining stage not-run with exit code ${NOT_RUN_EXIT_CODE}. These are the only commands to run: the contract's full ladder (./scripts/ci.sh --affected ...) runs once, at apply time, in the main checkout, and running it here only doubles the cost.
${targetedSpecs.map(spec => `   - ${spec.id}: ${spec.command}`).join('\n')}
3. Run git diff --check, inspect git status, and verify the path/action rules. Reject every untracked path except the exact requiredAddedPaths set (ignore .venv, .tmp, __pycache__, and other gitignored artifacts uv or the tests create).
4. Capture one deterministic exact patch without touching the index: first write git diff --binary --full-index --no-renames --no-ext-diff over the allowed tracked paths, then append one git diff --no-index --binary --full-index --no-ext-diff /dev/null <path> patch for each requiredAddedPaths entry in contract order (exit code 1 is expected when that no-index diff finds content). Save the combined bytes, compute SHA-256 and byte size from them, and report exact repo-relative changed/added/modified/deleted lists.
5. Persist the exact combined patch bytes outside the repository at /tmp/lawvm-norway-batches/${contract.id}/<sha256>.patch, where <sha256> is the value you computed. Create parent directories as needed. Re-read the file and require its SHA-256 and byte size to match before reporting artifactPath and artifactPersisted true. This file is the patch's identity: the human applies it, not the returned text.
6. Clean the isolated worktree by applying the combined captured patch in reverse (git apply -R) or by an equally explicit disposable-worktree proof. Do not use git restore. Confirm no tracked source change remains. The /tmp artifact must remain after cleanup.
7. Return the exact patch text and bounded evidence. If cleanup or any required command fails, return status abort.
`, {label: `implement:${contract.id}`, phase: 'Implement', effort: 'high', agentType: 'general-purpose', isolation: 'worktree', schema: PATCH_SCHEMA})

const implementationReasons = validatePatchResult(implementation, contract, facts.head, targetedSpecs, scopeMatchers)
if (implementationReasons.length) {
  const result = emptyReport('aborted', implementationReasons, {phase: 'Implement', facts, contract, contractPath, preflight})
  result.patch = implementation ? {
    sha256: implementation.patchSha256,
    sizeBytes: implementation.patchBytes,
    changedFiles: implementation.changedFiles,
  } : null
  result.targetedStages = implementation ? compactStages(implementation.stages) : []
  return result
}

const initialPatchInfo = inspectPatch(implementation.patchText)
const patchDeviations = scopeDeviations(initialPatchInfo, scopeMatchers, contract)
if (patchDeviations.length) log(`Patch stays inside the boundary but deviates from the contract manifest: ${patchDeviations.join('; ')}`)
const reviewContract = JSON.stringify({
  id: contract.id,
  classification: contract.classification,
  objective: contract.objective,
  scope: contract.scope,
  requirements: contract.requirements,
  invariants: contract.invariants,
  exclusions: contract.exclusions,
  stopConditions: contract.stopConditions,
  reviewFocus: contract.reviewFocus,
  fieldVerification: contract.fieldVerification,
  baseHead: facts.head,
  scopeDeviations: patchDeviations,
})

phase('Review')
log('Reviewing correctness and architecture independently.')
const rawReviews = await parallel([
  () => agent(`
Perform a READ-ONLY adversarial correctness review. Do not edit files.

Frozen contract:
${reviewContract}

Patch SHA-256: ${implementation.patchSha256}
Patch:
${implementation.patchText}

Assume the patch is wrong until repository and patch evidence show otherwise. Check actual behavior, type/runtime agreement, contract requirements, invariants, focused test adequacy, lost side effects, invalid path actions, and concrete regression scenarios. LawVM-specific checks: a compare-lane change must apply symmetrically to both compared trees and never mutate replay-authoritative state; new filtering/recovery/projection behavior must emit its typed receipt or projection (silent behavior change is a defect here even when tests pass); a text-normalization rule must be bounded — construct a realistic Norwegian legal text it would wrongly alter if you can. Report only actionable defects introduced or left unresolved by this patch; do not suggest later-batch work or style preferences. Set verdict to findings whenever you report any finding at all, including low-severity or non-blocking ones: whether a finding blocks is the adjudicator's decision, not yours. Give each finding an id unique within your own review; the workflow namespaces ids across reviewers. Run read-only commands through uv (uv run ...). Do not run ./scripts/ci.sh or full shard sweeps: the full ladder runs once, at apply time.
`, {label: `review:correctness:${contract.id}`, phase: 'Review', effort: 'high', agentType: 'general-purpose', schema: REVIEW_SCHEMA}),
  () => agent(`
Perform a READ-ONLY adversarial architecture and net-simplification review. Do not edit files.

Frozen contract:
${reviewContract}

Patch SHA-256: ${implementation.patchSha256}
Patch:
${implementation.patchText}

Reject scope expansion, missing required actions, compatibility layers, stubs, parallel models, broad frameworks, test weakening, moved complexity, or abstractions the contract does not require. LawVM-specific checks: new rules/receipts must follow the existing typed-carrier shapes beside them (same dataclass, same naming family, same projection lane), not introduce a second dialect; comment density and style must match the surrounding file; a change in the compare-only lane must not widen the consolidation's authority over replay (AGENTS.md: the oracle is evidence, never repair permission). The frozen contract carries scopeDeviations: paths the patch touched that stay inside the contract boundary but are not on its manifest. These are yours to judge, not automatic failures. Report each deviation you judge unjustified as a finding, and say plainly in your summary which ones you accepted and why. Treat a paragraph-long comment defending a decision as a signal that the code is working around something rather than solving it. Approve only when the patch is the smallest coherent implementation. Set verdict to findings whenever you report any finding at all, including low-severity or non-blocking ones: whether a finding blocks is the adjudicator's decision, not yours. Give each finding an id unique within your own review; the workflow namespaces ids across reviewers. Run read-only commands through uv (uv run ...). Do not run ./scripts/ci.sh or full shard sweeps: the full ladder runs once, at apply time.
`, {label: `review:architecture:${contract.id}`, phase: 'Review', effort: 'high', agentType: 'general-purpose', schema: REVIEW_SCHEMA}),
])
const reviews = normalizeReviews(rawReviews)

const reviewReasons = []
if (reviews.length !== 2 || reviews.some(review => !review)) reviewReasons.push('One or more independent reviewers returned no result')
if (!reviewReasons.length) {
  if (!sameStrings(reviews.map(review => review.kind), ['correctness', 'architecture'])) reviewReasons.push('Both reviewer roles were not completed')
  for (const review of reviews) {
    if (review.status !== 'completed' || review.verdict === 'unable') reviewReasons.push(`${review.kind} reviewer was unable to complete`)
    if (!review.baseHeadMatches || !review.patchPathsValid) reviewReasons.push(`${review.kind} reviewer found an invalid base or path set`)
  }
  reviewReasons.push(...validateReviews(reviews))
}
if (reviewReasons.length) {
  const result = emptyReport('aborted', reviewReasons, {phase: 'Review', facts, contract, contractPath, preflight, reviews: reviews.filter(Boolean)})
  result.patch = {sha256: implementation.patchSha256, sizeBytes: implementation.patchBytes, changedFiles: initialPatchInfo.paths}
  return result
}

phase('Adjudicate')
// An adjudicator may only confirm, reject, or deduplicate findings the reviewers raised, so with
// no findings there is nothing for it to partition and no fixer it could ask for.
const reviewFindingIds = new Set(reviews.flatMap(review => review.findings.map(finding => finding.id)))
const adjudication = reviewFindingIds.size === 0
  ? {
      status: 'completed',
      confirmedFindings: [],
      rejectedFindings: [],
      needsFixer: false,
      summary: 'Both reviewers approved with no findings, so there was nothing to adjudicate.',
    }
  : await agent(`
Adjudicate two READ-ONLY reviews of a frozen Norway batch patch. Do not edit files and do not invent findings.

Frozen contract:
${reviewContract}

Patch:
${implementation.patchText}

Reviews:
${JSON.stringify(reviews)}

You may confirm, reject, or deduplicate only findings whose IDs appear in the reviews. Confirm only concrete defects supported by repository and patch evidence. Reject style preferences, speculative concerns, later-batch work, or requirements absent from the contract. If a real defect requires a path or redesign outside the frozen contract, mark insideContract false rather than expanding scope. Separately, set blocksPatch to say whether the patch itself must not ship: true when the patch is defective, false when the patch is sound and the finding is residue it reveals or leaves behind outside this contract. Only blocksPatch true stops the run; a non-blocking finding is recorded in the report for a later batch, so justify blocksPatch false with the evidence that nothing the patch does is wrong. An insideContract defect is fixed here regardless of blocksPatch. For every finding you reject, give a one-line reason that says why it does not need fixing under this contract and what would change that answer. A rejected finding is kept in the report, so the reason is what a later reader has to go on. Run read-only commands through uv (uv run ...).
`, {label: `adjudicate:${contract.id}`, phase: 'Adjudicate', effort: 'high', agentType: 'general-purpose', schema: ADJUDICATION_SCHEMA})
log(reviewFindingIds.size === 0
  ? 'Both reviewers approved with no findings; no adjudication was required.'
  : `Adjudicating ${reviewFindingIds.size} finding(s) raised by the two reviewers.`)

const adjudicationReasons = []
if (!adjudication || adjudication.status !== 'completed') adjudicationReasons.push('Adjudicator returned no usable result')
if (adjudication) {
  for (const finding of adjudication.confirmedFindings) {
    if (!finding.sourceFindingIds.length || finding.sourceFindingIds.some(id => !reviewFindingIds.has(id))) adjudicationReasons.push('Adjudicator invented or lost a source finding ID')
    if (!finding.insideContract && finding.blocksPatch) adjudicationReasons.push('A blocking defect requires work outside the frozen contract')
  }
  if (adjudication.needsFixer !== fixableFindings(adjudication).length > 0) adjudicationReasons.push('Adjudicator fixer decision is inconsistent')
  adjudicationReasons.push(...validateAdjudicationPartition(reviews, adjudication))
}
if (adjudicationReasons.length) {
  const result = emptyReport('aborted', adjudicationReasons, {phase: 'Adjudicate', facts, contract, contractPath, preflight, reviews, adjudication})
  result.patch = {sha256: implementation.patchSha256, sizeBytes: implementation.patchBytes, changedFiles: initialPatchInfo.paths}
  return result
}

phase('Fix')
let fixer = null
let finalPatch = implementation
let finalReviews = reviews
let finalAdjudication = adjudication
if (adjudication.needsFixer) {
  log(`Applying ${fixableFindings(adjudication).length} adjudicated correction(s) in a fresh isolated worktree.`)
  fixer = await agent(`
Fix only the adjudicated findings in a fresh isolated worktree. Do not touch the user's main worktree.
Do not commit, stage, stash, reset, rebase, push, weaken tests, or edit outside the contract.

Initial HEAD must equal ${facts.head}.
Frozen contract:
${frozenContract}

Original patch:
${implementation.patchText}

Adjudicated findings (the only findings you may act on):
${JSON.stringify(fixableFindings(adjudication))}

First run ${corpusEnvLine} so the corpus archives resolve, and invoke every Python entry point through uv. Save the original patch and run git apply --check, then apply it. Make only the exact adjudicated corrections. Run the exact targeted command sequence and fail fast with exit code ${NOT_RUN_EXIT_CODE} for not-run stages. Run git diff --check and reject every untracked path except the exact requiredAddedPaths set (ignore .venv, .tmp, __pycache__, and other gitignored artifacts). Capture a deterministic complete replacement patch without touching the index: tracked diff first, then append one git diff --no-index patch from /dev/null for each required added path in contract order. Recompute SHA-256, byte size, and exact path classifications. Persist the exact replacement patch bytes at /tmp/lawvm-norway-batches/${contract.id}/<new sha256>.patch, re-read the file to confirm SHA-256 and byte size, and report artifactPath with artifactPersisted true; the artifact must remain after cleanup. Clean the worktree by reversing the replacement patch; do not use git restore. Return status abort if any correction requires broader scope or cleanup fails.

Targeted commands:
${targetedSpecs.map(spec => `- ${spec.id}: ${spec.command}`).join('\n')}
`, {label: `fix:${contract.id}`, phase: 'Fix', effort: 'high', agentType: 'general-purpose', isolation: 'worktree', schema: PATCH_SCHEMA})

  const fixerReasons = validatePatchResult(fixer, contract, facts.head, targetedSpecs, scopeMatchers)
  if (fixerReasons.length) {
    const result = emptyReport('aborted', fixerReasons, {phase: 'Fix', facts, contract, contractPath, preflight, reviews, adjudication})
    result.patch = fixer ? {sha256: fixer.patchSha256, sizeBytes: fixer.patchBytes, changedFiles: fixer.changedFiles} : null
    return result
  }
  finalPatch = fixer

  log('Re-reviewing the replacement patch independently; no second fixer is permitted.')
  finalReviews = await parallel([
    () => agent(`
Perform a READ-ONLY final adversarial correctness review of the replacement patch. Do not edit files. Verify the frozen contract, every original adjudicated defect, and any new regression introduced by the correction. Report only concrete defects. Run read-only commands through uv (uv run ...).

Frozen contract:
${reviewContract}

Previously confirmed defects:
${JSON.stringify(fixableFindings(adjudication))}

Replacement patch:
${fixer.patchText}
`, {label: `review:final-correctness:${contract.id}`, phase: 'Review', effort: 'high', agentType: 'general-purpose', schema: REVIEW_SCHEMA}),
    () => agent(`
Perform a READ-ONLY final adversarial architecture and correction-scope review of the replacement patch. Do not edit files. Verify every hunk is within the frozen contract, no unadjudicated compatibility or cleanup work was added, and the patch remains a net simplification. Report only concrete defects. Run read-only commands through uv (uv run ...).

Frozen contract:
${reviewContract}

Previously confirmed defects:
${JSON.stringify(fixableFindings(adjudication))}

Original patch:
${implementation.patchText}

Replacement patch:
${fixer.patchText}
`, {label: `review:final-architecture:${contract.id}`, phase: 'Review', effort: 'high', agentType: 'general-purpose', schema: REVIEW_SCHEMA}),
  ])
  finalReviews = normalizeReviews(finalReviews)
  const finalReviewReasons = []
  if (finalReviews.length !== 2 || finalReviews.some(review => !review)) finalReviewReasons.push('One or more final reviewers returned no result')
  if (!finalReviewReasons.length) {
    if (!sameStrings(finalReviews.map(review => review.kind), ['correctness', 'architecture'])) finalReviewReasons.push('Both final reviewer roles were not completed')
    for (const review of finalReviews) {
      if (review.status !== 'completed' || review.verdict === 'unable') finalReviewReasons.push(`${review.kind} final reviewer was unable to complete`)
      if (!review.baseHeadMatches || !review.patchPathsValid) finalReviewReasons.push(`${review.kind} final reviewer found an invalid base or path set`)
    }
    finalReviewReasons.push(...validateReviews(finalReviews))
  }
  if (finalReviewReasons.length) return emptyReport('aborted', finalReviewReasons, {phase: 'Review', facts, contract, contractPath, preflight, reviews: finalReviews, adjudication})

  finalAdjudication = await agent(`
Adjudicate the final READ-ONLY reviews of the replacement patch. Do not edit files and do not invent findings. Partition every final reviewer finding exactly once as confirmed or rejected using patch and repository evidence. No second fixer is allowed, so any confirmed defect aborts the batch. For every finding you reject, give a one-line reason that says why it does not need fixing under this contract and what would change that answer. A rejected finding is kept in the report, so the reason is what a later reader has to go on. Run read-only commands through uv (uv run ...).

Frozen contract:
${reviewContract}

Replacement patch:
${fixer.patchText}

Final reviews:
${JSON.stringify(finalReviews)}
`, {label: `adjudicate:final:${contract.id}`, phase: 'Adjudicate', effort: 'high', agentType: 'general-purpose', schema: ADJUDICATION_SCHEMA})
  const finalAdjudicationReasons = []
  if (!finalAdjudication || finalAdjudication.status !== 'completed') finalAdjudicationReasons.push('Final adjudicator returned no usable result')
  if (finalAdjudication) {
    finalAdjudicationReasons.push(...validateAdjudicationPartition(finalReviews, finalAdjudication))
    if (fixableFindings(finalAdjudication).length || finalAdjudication.confirmedFindings.some(finding => finding.blocksPatch) || finalAdjudication.needsFixer) finalAdjudicationReasons.push('Replacement patch still has a confirmed defect; bounded fixer cycle is exhausted')
  }
  if (finalAdjudicationReasons.length) return emptyReport('aborted', finalAdjudicationReasons, {phase: 'Adjudicate', facts, contract, contractPath, preflight, reviews: finalReviews, adjudication: finalAdjudication})
} else {
  log('No adjudicated corrections remain; retaining the implementation patch unchanged.')
}

const finalPatchInfo = inspectPatch(finalPatch.patchText)
const finalPatchReasons = validatePatchResult(finalPatch, contract, facts.head, targetedSpecs, scopeMatchers)
if (finalPatchReasons.length) {
  const result = emptyReport('aborted', finalPatchReasons, {phase: 'Fix', facts, contract, contractPath, preflight, reviews: finalReviews, adjudication: finalAdjudication})
  result.patch = {sha256: finalPatch.patchSha256, sizeBytes: finalPatch.patchBytes, changedFiles: finalPatchInfo.paths}
  return result
}

const expectedArtifactPath = `/tmp/lawvm-norway-batches/${contract.id}/${finalPatch.patchSha256}.patch`

phase('Report')
// No agent runs the full ladder. It runs exactly once, at apply time, in the main checkout, where
// a failure is reversible with git apply -R on a clean committed tree and the error is a command
// output in a terminal rather than testimony inside a schema. The report hands the human the
// ladder under humanVerification, and the artifact the implementer persisted is what gets applied:
// its SHA-256 is re-checked by the human, so no second agent needs to hash the same file.
log(`Batch ${contract.id} is reviewed and ready for the human apply step; nothing was applied or merged.`)

return {
  reportVersion: 1,
  workflow: WORKFLOW,
  batchId: contract.id,
  status: 'reviewed-patch-ready',
  merged: false,
  phase: 'Report',
  base: {
    branch: contract.branch,
    productBaseline: facts.productBaseline,
    runHead: facts.head,
  },
  inputs: {
    contractPath,
    contractSha256: facts.contractSha256,
    progressSha256: facts.progressSha256,
    sourceReviewSha256: facts.sourceReviewSha256,
    workflowSha256: facts.workflowSha256,
  },
  preflight: {
    committedDriftPaths: facts.committedDriftPaths,
    dirtyPaths: facts.dirtyPaths,
    failedContractChecks: [],
    summary: preflight.summary,
  },
  patch: {
    path: expectedArtifactPath,
    scopeDeviations: patchDeviations,
    sha256: finalPatch.patchSha256,
    sizeBytes: finalPatch.patchBytes,
    changedFiles: finalPatchInfo.paths,
    addedFiles: finalPatchInfo.added,
    modifiedFiles: finalPatchInfo.modified,
    deletedFiles: finalPatchInfo.deleted,
  },
  // Nothing in this workflow applies the patch or runs the full ladder. These are the checks that
  // decide whether it lands, and they are the human's to run, in order, in the main checkout:
  // the workflow never proves its own artifact to itself. A ladder failure after apply is
  // recovered with git apply -R.
  humanVerification: {
    expectedSha256: finalPatch.patchSha256,
    expectedBytes: finalPatch.patchBytes,
    commands: [
      `git -C ${facts.repositoryRoot} status --porcelain --untracked-files=all`,
      `sha256sum ${expectedArtifactPath}`,
      `git -C ${facts.repositoryRoot} apply --check ${expectedArtifactPath}`,
      `git -C ${facts.repositoryRoot} apply ${expectedArtifactPath}`,
    ],
    applyLadder: fullSpecs.map(spec => ({id: spec.id, command: spec.command})),
  },
  targetedStages: compactStages(finalPatch.stages),
  reviews: compactReviews(finalReviews),
  adjudication: {
    initialConfirmedFindingCount: adjudication.confirmedFindings.length,
    finalConfirmedFindingCount: finalAdjudication.confirmedFindings.length,
    rejectedFindings: fixer
      ? [...resolveRejected(reviews, adjudication), ...resolveRejected(finalReviews, finalAdjudication)]
      : resolveRejected(reviews, adjudication),
    fixerRan: Boolean(fixer),
    // Both adjudications, because the fixer clears the first one: residue raised before the fixer
    // ran would vanish from the report if only the final adjudication counted.
    residue: resolveResidue(fixer ? [adjudication, finalAdjudication] : [adjudication]),
    summary: finalAdjudication.summary,
  },
  fieldVerification: contract.fieldVerification,
  suggestedProgressStatus: 'reviewed-patch-ready',
  abortReasons: [],
  summary: 'The isolated patch passed the targeted stages and both adversarial reviews and is ready for the human apply step, which runs the full frozen ladder; it was not applied or merged.',
}

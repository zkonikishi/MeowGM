'use strict';
// Proposed read-only consumer. No HTTP, local settings write or authority inference.
const object = value => value && typeof value === 'object' && !Array.isArray(value);
const opaque = value => typeof value === 'string' && /^[A-Za-z0-9._:-]{1,128}$/.test(value);
const decimal = value => typeof value === 'string' && /^(0|[1-9][0-9]{0,18})$/.test(value) && BigInt(value) <= 9223372036854775807n;
function consumeSnapshot(snapshot, target, nowMs) {
  const unavailable = () => ({available: false, message: '未就绪', writeEnabled: false});
  if (!object(snapshot) || !object(target) || !Number.isSafeInteger(nowMs) || snapshot.version !== 'gm-access-snapshot-v1' || snapshot.available !== true) return unavailable();
  if (!opaque(snapshot.requestId) || snapshot.requestId !== target.requestId) return unavailable();
  for (const key of ['settingsRevision', 'observationVersion']) {
    const expected = target['expected' + key[0].toUpperCase() + key.slice(1)];
    if (expected !== undefined && (!opaque(expected) || snapshot[key] !== expected)) return unavailable();
  }
  if (!opaque(snapshot.instanceId) || snapshot.instanceId !== target.instanceId || !opaque(snapshot.realm) || snapshot.realm !== target.realm ||
      !decimal(snapshot.accountId) || snapshot.accountId === '0' || snapshot.accountId !== target.accountId ||
      !decimal(snapshot.characterId) || BigInt(snapshot.characterId) < 1n || BigInt(snapshot.characterId) > 65535n || snapshot.characterId !== target.characterId ||
      !opaque(snapshot.settingsRevision) || typeof snapshot.observationVersion !== 'string' || !/^[a-f0-9]{64}$/.test(snapshot.observationVersion) || !object(snapshot.access) ||
      !Number.isSafeInteger(snapshot.observedAtMs) || !Number.isSafeInteger(snapshot.validUntilMs) ||
      snapshot.observedAtMs > nowMs || snapshot.validUntilMs <= nowMs || snapshot.validUntilMs <= snapshot.observedAtMs ||
      snapshot.validUntilMs - snapshot.observedAtMs > 30000) return unavailable();
  for (const key of ['ignoreDailyEntryLimits', 'ignoreWeeklyEntryLimits']) if (typeof snapshot.access[key] !== 'boolean') return unavailable();
  if (!Array.isArray(snapshot.towers) || snapshot.towers.length !== 2) return unavailable();
  const ids = new Set(), towers = [];
  for (const tower of snapshot.towers) {
    if (!object(tower) || !['origin', 'dazzlement'].includes(tower.id) || ids.has(tower.id)) return unavailable();
    ids.add(tower.id);
    const row = {id: tower.id};
    for (const period of ['daily', 'weekly']) {
      const counter = tower[period];
      if (!object(counter) || typeof counter.applicable !== 'boolean') return unavailable();
      if (!counter.applicable) {
        if (counter.used !== null || counter.naturalLimit !== null || counter.effectiveLimit !== null || counter.periodKey !== null) return unavailable();
        row[period] = {applicable: false}; continue;
      }
      const ignored = snapshot.access[period === 'daily' ? 'ignoreDailyEntryLimits' : 'ignoreWeeklyEntryLimits'];
      if (!decimal(counter.used) || !decimal(counter.naturalLimit) || !opaque(counter.periodKey) ||
          (ignored ? counter.effectiveLimit !== null : counter.effectiveLimit !== counter.naturalLimit)) return unavailable();
      row[period] = {applicable: true, used: counter.used, naturalLimit: counter.naturalLimit,
        effectiveLimit: counter.effectiveLimit, periodKey: counter.periodKey, ignored};
    }
    towers.push(row);
  }
  return {available: true, settingsRevision: snapshot.settingsRevision, observationVersion: snapshot.observationVersion,
    observedAtMs: snapshot.observedAtMs, towers, writeEnabled: false};
}
// Explicit adapter for the reviewed observation-v2 producer only, not a shape fallback.
// It normalizes transport representation; it neither authenticates nor recomputes hashes.
function consumeObservationV2(snapshot, target, nowMs) {
  if (!object(snapshot) || !object(snapshot.towers) || Array.isArray(snapshot.towers) ||
      Object.keys(snapshot.towers).sort().join(',') !== 'dazzlement,origin' ||
      typeof snapshot.observationVersion !== 'string' || !/^[A-Fa-f0-9]{64}$/.test(snapshot.observationVersion)) {
    return {available:false, message:'未就绪', writeEnabled:false};
  }
  return consumeSnapshot({...snapshot, observationVersion:snapshot.observationVersion.toLowerCase(),
    towers:['origin','dazzlement'].map(id => ({id, daily:snapshot.towers[id]?.daily,
      weekly:snapshot.towers[id]?.weekly}))}, target, nowMs);
}
module.exports = {consumeSnapshot, consumeObservationV2};

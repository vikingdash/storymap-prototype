// Lookup helpers so any screen can resolve an evidenceId or sourceId into displayable detail
// without duplicating the join logic. Everything here reads from the already-validated dataset.

export function buildEvidenceIndex(dataset) {
  const evidenceById = new Map(dataset.evidence.map((e) => [e.id, e]));
  const sourceById = new Map(dataset.sources.map((s) => [s.id, s]));

  return {
    getEvidence(evidenceId) {
      return evidenceById.get(evidenceId) || null;
    },
    getSource(sourceId) {
      return sourceById.get(sourceId) || null;
    },
    getEvidenceWithSource(evidenceId) {
      const item = evidenceById.get(evidenceId);
      if (!item) return null;
      return { evidence: item, source: sourceById.get(item.sourceId) || null };
    },
    getEvidenceForSource(sourceId) {
      return dataset.evidence.filter((e) => e.sourceId === sourceId);
    },
    allSourcesWithEvidence() {
      return dataset.sources.map((source) => ({
        source,
        evidence: dataset.evidence.filter((e) => e.sourceId === source.id),
      }));
    },
  };
}

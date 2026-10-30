import { fieldRect, rectsOverlap } from './geometry';
import { layoutText, resolveText, type Overflow } from './layout';
import type { TextField } from './types';
import { fieldLabel, SCENARIOS, type Scenario } from './variables';

export interface FitIssue {
  fieldId: string;
  label: string;
  scenario: Exclude<Scenario, 'custom' | 'empty'>;
  overflow: Overflow;
  fontSize: number;
}

export interface OverlapIssue {
  a: string;
  b: string;
  labels: [string, string];
}

// lays out each field with the typical and long sample values
export function fitCheck(fields: TextField[]): { issues: FitIssue[]; overlaps: OverlapIssue[]; byField: Map<string, FitIssue[]> } {
  const issues: FitIssue[] = [];
  for (const scenario of ['typical', 'long'] as const) {
    for (const f of fields) {
      if (f.kind !== 'variable') continue;
      const text = resolveText(f, SCENARIOS[scenario].values);
      if (text === null) continue;
      const lay = layoutText(text, f);
      if (lay.overflow !== 'none') issues.push({ fieldId: f.id, label: fieldLabel(f), scenario, overflow: lay.overflow, fontSize: lay.fontSize });
    }
  }
  const overlaps: OverlapIssue[] = [];
  for (let i = 0; i < fields.length; i++) {
    for (let j = i + 1; j < fields.length; j++) {
      if (rectsOverlap(fieldRect(fields[i]), fieldRect(fields[j]))) {
        overlaps.push({ a: fields[i].id, b: fields[j].id, labels: [fieldLabel(fields[i]), fieldLabel(fields[j])] });
      }
    }
  }
  const byField = new Map<string, FitIssue[]>();
  for (const issue of issues) byField.set(issue.fieldId, [...(byField.get(issue.fieldId) ?? []), issue]);
  return { issues, overlaps, byField };
}

export function describe(issue: FitIssue): string {
  const where = issue.scenario === 'long' ? 'with long values' : 'with typical values';
  if (issue.overflow === 'truncated') return `${issue.label} is cut off ${where}`;
  if (issue.overflow === 'wrapped') return `${issue.label} wraps to 2 lines ${where}`;
  return `${issue.label} shrinks to ${issue.fontSize}px ${where}`;
}

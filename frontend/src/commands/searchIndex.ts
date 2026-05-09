
import type { Command } from "./registry";

interface IndexEntry {
  command: Command;
  tokens: string[];       
  labelLower: string;     
  descLower: string;      
}

export class SearchIndex {
  private entries: IndexEntry[] = [];

  build(commands: Command[]): void {
    this.entries = commands.map((cmd) => {
      const tokens = new Set<string>();

      for (const word of cmd.label.toLowerCase().split(/[\s\-_:/.]+/)) {
        if (word.length > 0) tokens.add(word);
      }

      for (const word of cmd.description.toLowerCase().split(/[\s\-_:/.]+/)) {
        if (word.length > 1) tokens.add(word);
      }

      for (const kw of cmd.keywords) {
        tokens.add(kw.toLowerCase());
      }

      tokens.add(cmd.category);

      return {
        command: cmd,
        tokens: Array.from(tokens),
        labelLower: cmd.label.toLowerCase(),
        descLower: cmd.description.toLowerCase(),
      };
    });
  }

  search(query: string, limit: number = 20): Command[] {
    if (!query.trim()) {
      
      return this.entries
        .filter((e) => !e.command.id.startsWith("file:") && !e.command.id.startsWith("fn:"))
        .slice(0, limit)
        .map((e) => e.command);
    }

    const q = query.toLowerCase().trim();
    const qTokens = q.split(/\s+/).filter(Boolean);

    const scored: { entry: IndexEntry; score: number }[] = [];

    for (const entry of this.entries) {
      let score = 0;

      if (entry.labelLower === q) {
        score += 100;
      }
      
      else if (entry.labelLower.startsWith(q)) {
        score += 60;
      }
      
      else if (entry.labelLower.includes(q)) {
        score += 40;
      }

      for (const qt of qTokens) {
        for (const token of entry.tokens) {
          if (token === qt) {
            score += 20;
          } else if (token.startsWith(qt)) {
            score += 12;
          } else if (token.includes(qt)) {
            score += 6;
          }
        }
      }

      if (entry.descLower.includes(q)) {
        score += 8;
      }

      if (!entry.command.id.startsWith("file:") && !entry.command.id.startsWith("fn:")) {
        score += 2;
      }

      if (score === 0) {
        const fuzzyScore = fuzzyMatch(q, entry.labelLower);
        if (fuzzyScore > 0) {
          score += fuzzyScore;
        }
      }

      if (score > 0) {
        scored.push({ entry, score });
      }
    }

    scored.sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score;
      return a.entry.labelLower.localeCompare(b.entry.labelLower);
    });

    return scored.slice(0, limit).map((s) => s.entry.command);
  }

  get size(): number {
    return this.entries.length;
  }
}

function fuzzyMatch(query: string, target: string): number {
  let qi = 0;
  let score = 0;
  let consecutive = 0;

  for (let ti = 0; ti < target.length && qi < query.length; ti++) {
    if (target[ti] === query[qi]) {
      qi++;
      consecutive++;
      score += consecutive; 
    } else {
      consecutive = 0;
    }
  }

  return qi === query.length ? Math.max(score * 0.5, 1) : 0;
}

export const searchIndex = new SearchIndex();

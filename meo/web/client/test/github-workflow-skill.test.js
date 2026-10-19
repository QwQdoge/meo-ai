import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';

const skill = readFileSync(new URL('../../../skills/github-development/SKILL.md', import.meta.url), 'utf8');
const picker = readFileSync(new URL('../src/meo/PluginDiscovery.tsx', import.meta.url), 'utf8');

test('Meo GitHub development Skill remains discoverable by the account importer', () => {
  assert.match(skill, /^---\nname: github-development\ndescription: .+\n---/);
  assert.match(picker, /owner: 'QwQdoge'/);
  assert.match(picker, /repo: 'meo-ai'/);
  assert.match(picker, /path: 'meo\/skills\/github-development\/SKILL\.md'/);
});

test('Coding Skill is workflow guidance, not permission or execution authority', () => {
  assert.match(skill, /does not install a tool/i);
  assert.match(skill, /separately authorized write operation/i);
  assert.match(skill, /cannot authorize/i);
  assert.match(skill, /Never.*re.?dispatch|instead of creating a second execution|reconnect/i);
});

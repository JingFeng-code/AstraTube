import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {coverageNotice} from '../src/utils.js'

const t = (key, ...args) => `${key}|${args.join('|')}`

test('涵蓋範圍受限時顯示略過段數與分析到的時間點', () => {
  assert.equal(coverageNotice({skipped: 3, covered_until: 3725}, t), 'stream.coverageLimited|3|1:02:05')
  assert.equal(coverageNotice({skipped: 3, covered_until: null}, t), 'stream.coverageLimited|3|')
})

test('沒有涵蓋範圍限制時不顯示提示', () => {
  for (const coverage of [null, undefined, {}, {skipped: 0, covered_until: 10}]) {
    assert.equal(coverageNotice(coverage, t), '')
  }
})

test('涵蓋範圍存進摘要結果，重新載入時由已存結果還原提示', () => {
  const hook = readFileSync(new URL('../src/hooks/useSummarizeStream.js', import.meta.url), 'utf8')
  assert.match(hook, /draft\.coverage_limit = \{ skipped: ev\.skipped/)
  assert.match(hook, /useState\(initialResult\?\.coverage_limit \|\| null\)/)
  assert.match(hook, /notice: coverageNotice\(coverage, t\)/)
})

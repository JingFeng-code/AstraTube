import test from 'node:test'
import assert from 'node:assert/strict'
import {activeCueIndex, visibleCues} from '../src/utils/subtitles.js'

const cues = [
  {start:0,end:4,text:'Hello'},
  {start:4,end:9,text:'Welcome',translation:'歡迎'},
  {start:11,end:15,text:'Goodbye'},
]

test('active subtitles follow video time and stop in silent gaps',()=>{
  assert.equal(activeCueIndex(cues,0),0)
  assert.equal(activeCueIndex(cues,3.99),0)
  assert.equal(activeCueIndex(cues,4),1)
  assert.equal(activeCueIndex(cues,10),-1)
  assert.equal(activeCueIndex(cues,12),2)
  assert.equal(activeCueIndex(cues,16),-1)
  assert.equal(activeCueIndex([],5),-1)
})

test('searches source and translation without changing time order',()=>{
  assert.deepEqual(visibleCues(cues,'歡迎'),[cues[1]])
  assert.deepEqual(visibleCues(cues,'HELLO'),[cues[0]])
  assert.equal(visibleCues(cues,'').length,3)
})

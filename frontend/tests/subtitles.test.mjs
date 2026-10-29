import test from 'node:test'
import assert from 'node:assert/strict'
import {activeCueIndex, visibleCues, applyTranslations} from '../src/utils/subtitles.js'

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

test('partial translation only updates matching subtitle index',()=>{
  const changed = applyTranslations(cues, [{id:1,translation:'這是新的譯文'}, {id:19,translation:'忽略'}])
  assert.equal(changed[0].translation,undefined)
  assert.equal(changed[1].translation,'這是新的譯文')
  assert.equal(changed[1].start,4)
  assert.equal(changed[2].text,'Goodbye')
  assert.deepEqual(visibleCues(changed,'新的譯文'),[changed[1]])
  assert.equal(cues[1].translation,'歡迎')
})

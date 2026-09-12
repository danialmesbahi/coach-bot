import assert from 'node:assert/strict';
import { chatViewport } from '../src/lib/chat-viewport.ts';

// Portrait -> keyboard -> restored -> landscape -> portrait.
assert.deepEqual(chatViewport(844,844,0), {keyboardInset:0,keyboard:false});
assert.deepEqual(chatViewport(844,490,22), {keyboardInset:332,keyboard:true});
assert.deepEqual(chatViewport(844,844,0), {keyboardInset:0,keyboard:false});
assert.deepEqual(chatViewport(390,390,0), {keyboardInset:0,keyboard:false});
assert.deepEqual(chatViewport(844,844,0), {keyboardInset:0,keyboard:false});
// Browser chrome is not a keyboard; visible height still owns the geometry.
assert.deepEqual(chatViewport(844,760,0), {keyboardInset:0,keyboard:false});
console.log('chat viewport regression checks passed');
assert.deepEqual(chatViewport(844,844,84), {keyboardInset:0,keyboard:false});
assert.deepEqual(chatViewport(844,490,22), {keyboardInset:332,keyboard:true});

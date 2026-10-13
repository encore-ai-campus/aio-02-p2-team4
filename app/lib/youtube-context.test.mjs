import test from 'node:test';
import assert from 'node:assert/strict';
import * as youtubeContext from './youtube-context.ts';
import {formatYoutubePublishedAt, formatYoutubeViewCount, stripYoutubeApiDataForExport, youtubeThumbnailUrl} from './youtube-context.ts';

test('builds thumbnails only for supported HTTPS YouTube video links', () => {
 assert.equal(youtubeThumbnailUrl('https://www.youtube.com/watch?v=aB_12345678&feature=share'),'https://i.ytimg.com/vi/aB_12345678/mqdefault.jpg');
 assert.equal(youtubeThumbnailUrl('https://youtu.be/aB_12345678'),'https://i.ytimg.com/vi/aB_12345678/mqdefault.jpg');
 assert.equal(youtubeThumbnailUrl('https://youtube.com/shorts/aB_12345678'),'https://i.ytimg.com/vi/aB_12345678/mqdefault.jpg');
 for (const url of [
  'http://youtube.com/watch?v=aB_12345678',
  'https://youtube.com/watch?v=aB_12345678&v=cD_12345678',
  'https://youtube.com.evil.example/watch?v=aB_12345678',
  'https://example.com/watch?v=aB_12345678',
  'https://youtube.com/watch?v=short',
  'not a URL',
 ]) assert.equal(youtubeThumbnailUrl(url),null);
});

test('removes YouTube API title and comments from downloaded results', () => {
 const sources=[
  {id:'s1',sourceType:'유튜브',youtubeTitle:'API title',youtubeChannelTitle:'API channel',youtubePublishedAt:'2026-09-20T12:30:00Z',youtubeViewCount:'1234567',youtubeComments:['Raw comment'],youtubeDataStatus:'collected'},
  {id:'s2',sourceType:'한국 기사',youtubeTitle:null,youtubeComments:[],youtubeDataStatus:'not_applicable'},
 ];
 const stripped=stripYoutubeApiDataForExport(sources);
 assert.deepEqual(stripped[0],{...sources[0],youtubeTitle:null,youtubeChannelTitle:null,youtubePublishedAt:null,youtubeViewCount:null,youtubeComments:[],youtubeDataStatus:'not_applicable'});
 assert.deepEqual(stripped[1],sources[1]);
 assert.notEqual(stripped[0],sources[0]);
});

test('formats published dates and exact string view counts safely', () => {
 assert.equal(formatYoutubePublishedAt('2026-09-20T12:30:00Z'),'2026.09.20');
 assert.equal(formatYoutubePublishedAt('not-a-date'),null);
 assert.equal(formatYoutubeViewCount('12345678901234567890'),'12,345,678,901,234,567,890회');
 assert.equal(formatYoutubeViewCount('12 views'),null);
});

test('source labels distinguish collected comments from verified captions', () => {
 assert.equal(typeof youtubeContext.sourceAccessLabel,'function');
 const source={sourceType:'유튜브',accessStatus:'unavailable',youtubeDataStatus:'collected'};
 assert.equal(youtubeContext.sourceAccessLabel(source),'정보·댓글 수집 완료 · 자막 미확인');
 assert.equal(youtubeContext.sourceAccessLabel({...source,accessStatus:'verified'}),'정보·댓글 수집 완료 · 자막 확인');
 assert.equal(youtubeContext.sourceAccessLabel({...source,youtubeDataStatus:'not_configured'}),'유튜브 API 미설정 · 자막 미확인');
 assert.equal(youtubeContext.sourceAccessLabel({...source,youtubeDataStatus:'unavailable'}),'정보·댓글 조회 실패 · 자막 미확인');
 assert.equal(youtubeContext.sourceAccessLabel({...source,accessStatus:'candidate'}),'검색 후보');
 assert.equal(youtubeContext.sourceAccessLabel({sourceType:'웹',accessStatus:'unavailable'}),'접근 불가');
});

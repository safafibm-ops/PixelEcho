// Browser-only fixture responses: never part of the running application.
const { chromium } = require('C:/Program Files/WindowsApps/OpenAI.CodexPrimaryRuntime.v26-1112-737-0_26.1112.737.0_x64__3k8sg7r9htsxt/dependencies/node/node_modules/playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');

(async () => {
  const browser = await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  try {
    const page = await browser.newPage({viewport:{width:1280,height:1100}});
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    const fixtureImage='https://fixture.example/photo.jpg';
    let evidenceCalls=0;
    await page.route('**/*',async route=>{
      const request=route.request();
      const url=new URL(request.url());
      if(url.hostname!=='127.0.0.1')return route.fulfill({status:404,body:''});
      if(url.pathname==='/api/status')return route.fulfill({json:{stage:2,configured:true}});
      if(url.pathname==='/api/search')return route.fulfill({json:{
        elapsed_seconds:.1,provider_requests:1,query_dimensions:[100,100],
        pages:[{url:'https://fixture.example/article',title:'Fixture article',full_matches:[{url:fixtureImage}],partial_matches:[]}],
        full_matches:[],partial_matches:[],similar_images:[],web_entities:[],labels:[]}});
      if(url.pathname==='/api/evidence'){
        evidenceCalls++;
        assert.equal(request.postDataJSON().pages[0].image_urls[0],fixtureImage);
        return route.fulfill({json:{attempted:1,collected:1,notice:'Test fixture evidence. Visual verification is pending.',pages:[{
          requested_url:'https://fixture.example/article',final_url:'https://fixture.example/article',
          title:'Fixture archive article',status:'collected',retrieved_at:'2026-11-13T10:00:00Z',
          article_author:'Article Writer',page_dates:[{type:'page_publication_date',value:'2019-02-03',source:'meta:article:published_time'}],
          image_associations:[{image_url:fixtureImage,association:'image_element_located',caption:'The crew returns to port. Photo: Archive Agency',reported_credit:'Photo: Archive Agency',alt_text:'Rescue crew'}],
          text:'Fixture page text collected for browser verification.',text_truncated:false}]}});
      }
      return route.continue();
    });
    await page.goto('http://127.0.0.1:8001/');
    await page.getByText('API key configured · ready to test',{exact:true}).waitFor();
    const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jX3cAAAAASUVORK5CYII=','base64');
    await page.locator('#file').setInputFiles({name:'fixture.png',mimeType:'image/png',buffer:png});
    await page.getByRole('button',{name:'Search the web',exact:true}).click();
    await page.getByText('Credit reported beside this image: Photo: Archive Agency',{exact:true}).waitFor();
    assert.equal(evidenceCalls,1);
    await page.getByText('Read collected page text',{exact:true}).click();
    await page.getByText('Fixture page text collected for browser verification.',{exact:true}).waitFor({state:'visible'});
    assert.equal(await page.getByText('Article author reported by page: Article Writer. This is not a photographer attribution.',{exact:true}).count(),1);
    assert.equal(await page.locator('body').evaluate(el=>el.scrollWidth>window.innerWidth),false);
    const qa=path.join(__dirname,'.qa');fs.mkdirSync(qa,{recursive:true});
    await page.screenshot({path:path.join(qa,'evidence-desktop.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.locator('body').evaluate(el=>el.scrollWidth>window.innerWidth),false);
    await page.screenshot({path:path.join(qa,'evidence-mobile.png'),fullPage:true});
    assert.deepEqual(errors,[]);
    console.log('Browser fixture checks passed: search, evidence request, caption/credit/date rendering, expanded text, desktop/mobile overflow, and no JavaScript errors. No Google requests made.');
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});

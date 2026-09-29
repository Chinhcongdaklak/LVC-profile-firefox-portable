(async()=>{
  var TARGET=__TARGET__;
  var sleep=ms=>new Promise(r=>setTimeout(r,ms));
  function clean(t){return (t||"").replace(/[\u200b-\u200f\u034f\ufeff\u00ad]/g,"").replace(/\s+/g," ").trim();}
  var feed=null;
  for(var w=0;w<30;w++){                 // cho toi 30s cho React ve xong feed (KHONG cuon
    feed=document.querySelector('[role="feed"]');   // de bai tren cung khong bi ao hoa mat)
    if(feed && feed.children.length>2) break;
    await sleep(1000);
  }
  if(!feed) return JSON.stringify({error:"khong thay role=feed (feed chua render / chua vao duoc nhom)"});
  window.scrollTo(0,0); await sleep(800);   // ve dau feed, bat dau tu bai moi nhat

  function authorOf(k){
    var al=[...k.querySelectorAll('a[aria-label]')].map(a=>a.getAttribute("aria-label")).find(x=>/, xem tin$|, xem trang cá nhân$/.test(x||""));
    if(al) return clean(al.replace(/,[^,]*$/,""));
    var s=k.querySelector('h2 a,h3 a,h4 a,strong a,span strong');
    if(s){var t=clean(s.textContent);if(t)return t;}
    var ua=k.querySelector('a[href*="/user/"]');
    return ua?clean(ua.textContent):"";
  }
  function permaOf(k){
    var a=k.querySelector('a[href*="/stories/"],a[href*="/posts/"],a[href*="/permalink/"]');
    if(a) return a.href.split("?")[0];
    var ph=k.querySelector('a[href*="/photo/?fbid="]');
    if(ph){var m=ph.href.match(/set=pcb\.(\d+)/);if(m)return location.origin+location.pathname.replace(/\/+$/,"")+"/posts/"+m[1];}
    return "";
  }
  function idOf(k,perma,cap){
    var m=(perma||"").match(/\/stories\/(\d+)|\/posts\/(\d+)|\/permalink\/(\d+)/);
    if(m) return m[1]||m[2]||m[3];
    var ph=k.querySelector('a[href*="fbid="]');if(ph){var f=ph.href.match(/fbid=(\d+)/);if(f)return "f"+f[1];}
    return cap?("c"+cap.slice(0,40)):null;
  }

  var posts={}, order=[];

  // NET AN TOAN: dong hop "Tao bai viet" neu lo mo ra khi quet. Bam X, roi neu
  // hien hop "Bo bai viet?" thi bam Bo -> tuyet doi khong de composer mo (tranh
  // lo bam Dang / dinh bai rac). Tra ve true neu vua dong mot composer.
  function closeComposer(){
    var dlg=null;
    for(var d of document.querySelectorAll('[role="dialog"]')){
      var t=(d.innerText||"");
      if(/Tạo bài viết|Bạn viết gì|Create post|Write something|Bạn đang nghĩ gì/i.test(t)){dlg=d;break;}
    }
    if(!dlg) return false;
    // Nut X: aria-label THUC TE la "Dong hop thoai cua cong cu tao" (khong phai
    // dung "Dong") -> khop CHUA. Tim trong dialog, khong co thi tim ca trang.
    var x=dlg.querySelector('[aria-label*="Đóng"],[aria-label*="Close"]')
        || document.querySelector('[role="dialog"] [aria-label*="Đóng hộp thoại"],[aria-label*="Close dialog"]');
    if(x){try{x.click();}catch(e){}}
    else{ // du phong: Escape
      try{document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',keyCode:27,which:27,bubbles:true}));}catch(e){}
    }
    // Neu hien hop "Bo bai viet?" (khi composer co noi dung) -> bam Bo/Discard.
    setTimeout(function(){
      for(var d2 of document.querySelectorAll('[role="dialog"]')){
        if(/Bỏ bài viết|Discard post|Hủy bài|Bỏ thay đổi|Discard changes/i.test(d2.innerText||"")){
          for(var b of d2.querySelectorAll('[role="button"],button')){
            if(/^(Bỏ|Discard|Hủy|Bỏ bài viết|Discard post)$/i.test((b.innerText||"").trim())){try{b.click();}catch(e){}return;}
          }
        }
      }
    },500);
    return true;
  }

  // Nut "Xem them" cua CAPTION nam trong khoi van ban bai viet (div[dir="auto"]).
  // KHONG bam nut ngoai caption (vd o soan bai) -> tranh mo composer.
  function isCaptionSeeMore(b){
    if(!/^(xem thêm|see more)$/i.test((b.innerText||"").trim())) return false;
    for(var p=b; p && p!==document.body; p=p.parentElement){
      if(p.getAttribute && p.getAttribute("role")==="dialog") return false;  // trong hop thoai -> bo
      if(p.matches && p.matches('div[dir="auto"]')) return true;             // trong caption -> OK
    }
    return false;
  }

  function expandAll(){
    if(closeComposer()) return;    // co composer dang mo thi dong roi thoi, khong bam gi them luot nay
    for(var k of feed.children){
      if((k.innerText||"").trim().length<25) continue;
      [...k.querySelectorAll('[role="button"]')].forEach(function(b){
        if(isCaptionSeeMore(b)){try{b.click();}catch(e){}}
      });
    }
  }
  function collect(){
    for(var k of feed.children){
      if((k.innerText||"").trim().length<25) continue;
      var best="";
      for(var d of k.querySelectorAll('div[dir="auto"]')){var t=clean(d.innerText);if(!t)continue;if(/^(thích|bình luận|chia sẻ|·)$/i.test(t))continue;if(t.length>best.length)best=t;}
      best=best.replace(/\s*(Xem thêm|See more)\s*$/,"");
      var perma=permaOf(k);
      var id=idOf(k,perma,best);
      if(!id||posts[id]) continue;
      var author=authorOf(k);
      if(best===author) best="";
      var imgs=[];
      for(var im of k.querySelectorAll('img')){var s=im.currentSrc||im.src||"";if(!/t39\.30808|scontent/.test(s))continue;if(im.getBoundingClientRect().width<150)continue;if(imgs.indexOf(s)<0)imgs.push(s);}
      // Video: lay LINK TRANG (tai duoc) thay vi blob src (blob vo dung ngoai trinh duyet).
      // Uu tien /videos//reel//watch?v= trong anchor; neu khong co thi bocs video id
      // trong HTML (React giau link) roi dung watch?v=<id> (yt-dlp tai tot).
      var vids=[];
      function addVid(u){if(!u)return;var c=u.split("?")[0];if(c&&vids.indexOf(c)<0)vids.push(c);}
      for(var va of k.querySelectorAll('a[href*="/videos/"],a[href*="/reel/"],a[href*="/watch/?v="]')){
        addVid(va.href);
      }
      if(!vids.length){
        var vh=k.innerHTML, mm, re1=/\/videos\/(?:pcb\.\d+\/)?(\d{8,})/g;
        while((mm=re1.exec(vh))) addVid("https://www.facebook.com/watch/?v="+mm[1]);
        if(!vids.length){var re2=/[?&]v=(\d{8,})/g;while((mm=re2.exec(vh)))addVid("https://www.facebook.com/watch/?v="+mm[1]);}
      }
      var hasVideoEl=!!k.querySelector('video');
      if(hasVideoEl && !vids.length) vids.push(perma||location.href);  // cung duong -> link mo (co the /stories/)
      var fmt=(vids.length||hasVideoEl)?"Video":(imgs.length>1?"Album":(imgs.length?"Ảnh":(best?"Text":"Khác")));
      posts[id]={id:id,author:author,caption:best.slice(0,3000),permalink:perma,images:imgs,videos:vids,fmt:fmt};
      order.push(id);
    }
  }
  closeComposer();                 // phong khi vao trang da san mo composer
  expandAll(); await sleep(1300); collect();

  // CUON THEO TIEN DO, khong theo so luot cung. Truoc day: 25 luot x 1000px, ngu 1s
  // -> khong biet FB da tai them chua, khong biet da cham day -> nhom bai nang/proxy
  // cham chi ra 6-38/50 (do that 2026-09-05). Gio: moi vong cuon ~1 man hinh (de bai
  // nao cung vao khung nhin -> React ve ra -> gom duoc truoc khi bi ao hoa gỡ khoi
  // DOM), cham day thi DOI FB tai them (toi ~6s), 6 vong lien tiep khong them bai
  // va khong cao them = het feed that. Tran cung theo TARGET va ngan sach thoi gian
  // (BUDGET, Python dat) de luon tra ket qua truoc khi Python het gio.
  var BUDGET=__BUDGET_MS__, MAX_ROUNDS=Math.max(40, TARGET*4);
  var log=[], rounds=0, stall=0, tBat=Date.now();
  function cao(){return Math.max(document.body.scrollHeight||0, document.documentElement.scrollHeight||0);}
  function chamDay(){return window.scrollY + window.innerHeight >= cao() - 300;}
  function bamXemThemBai(){        // vai nhom FB hien nut "Xem them bai viet" thay vi tu tai
    // CHI tim trong vung feed (khong ca trang) va CHI dung chu nay -> khong bam nham
    // nut "Hien thi them" cua binh luan/menu (phat hien review sprint 1).
    var vung=feed.parentElement||feed;
    for(var b of vung.querySelectorAll('[role="button"],a[role="link"]')){
      if(!/^(xem thêm bài viết|see more posts)$/i.test((b.innerText||"").trim())) continue;
      try{b.click();}catch(e){} return true;
    }
    return false;
  }
  while(order.length<TARGET && rounds<MAX_ROUNDS && Date.now()-tBat<BUDGET){
    rounds++;
    closeComposer();               // moi vong: dong composer neu lo mo, roi moi cuon
    var truoc=order.length, caoTruoc=cao();
    window.scrollBy(0, Math.max(600, Math.round(window.innerHeight*0.85)));
    await sleep(700); expandAll(); await sleep(500); collect();
    if(chamDay() && order.length<TARGET){
      // Cham day phan da tai: doi FB tai them (bat nut "Xem them" neu co), toi ~6s.
      if(stall>=1) bamXemThemBai();
      var cho=0;
      while(cho<6000 && cao()<=caoTruoc+50 && Date.now()-tBat<BUDGET){ await sleep(500); cho+=500; }
      expandAll(); await sleep(300); collect();
    }
    if(order.length>truoc || cao()>caoTruoc+50) stall=0; else stall++;
    log.push("v"+rounds+": "+order.length+" bai, cao "+cao()+"px"+(stall?", dung "+stall:""));
    if(stall>=6) break;           // het feed that (khong them bai, khong cao them)
  }
  closeComposer();                 // truoc khi tra ket qua, dam bao khong con composer mo
  // Ly do dung -> UI noi dung su that (du / nhom chi co N bai / het gio / tran).
  var stop = order.length>=TARGET ? "du" : (stall>=6 ? "het_feed"
             : (Date.now()-tBat>=BUDGET ? "het_gio" : "tran"));
  return JSON.stringify({count:order.length,posts:order.slice(0,TARGET).map(id=>posts[id]),
                         rounds:rounds,log:log.slice(-40),ms:Date.now()-tBat,stop:stop});
})()

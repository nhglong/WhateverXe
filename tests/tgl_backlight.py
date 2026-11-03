#!/usr/bin/env python3
"""Replay the native TGL brightness wrapper, including cold startup and short routing."""
from pathlib import Path
import re,subprocess,tempfile
root=Path(__file__).resolve().parents[1]
source=(root/'WhateverXe/kern_xe.cpp').read_text()
body=re.search(r'uint32_t XE::wrapTGLPanelBacklight\(.*?\n\}',source,re.S)[0]
install=source[source.index('   // TGL_BACKLIGHT_MINIMUM_INSTALL:'):source.index('   // TGL_BACKLIGHT_MINIMUM_INSTALL_END')]
code=r'''
#include "kern_tgl_backlight.hpp"
#include "kern_xelp_platform.hpp"
#include <cassert>
#include <cstring>
#include <cstdio>
#include <vector>
#define FunctionCast(fn,p) reinterpret_cast<decltype(&fn)>(p)
struct IORegistryEntry {
 static IORegistryEntry *getRegistryRoot(){static IORegistryEntry root;return &root;}
 void setProperty(const char *,bool){}
};
struct KernelPatcher {
 unsigned routes=0;bool fail=false;uintptr_t delta=0;
 struct RouteRequest {template<class F> RouteRequest(const char *s,F,uintptr_t&){assert(strstr(s,"hwSetBacklight"));}};
 uintptr_t solveSymbol(unsigned,const char *s,uintptr_t address,size_t){assert(strstr(s,"hwSetBacklight"));return address+0x4a56a+delta;}
 bool routeMultipleShort(unsigned,RouteRequest*,unsigned count,uintptr_t,size_t){assert(count==1);++routes;return !fail;}
 void clearError(){}
};
struct XE {
 static XE *callbackXE;
 bool tglActive=true,adlsDisplaySelected=false,display13FramebufferRequested=false;
 struct {XELP::Family family=XELP::Family::TigerLake;}xeProfile;
 struct {struct {bool backlightValid=true,pwmPresent=true,minimumBrightnessValid=true;uint32_t minimumBrightness=3;} panel;}firmwarePorts;
 void *tglObservationController=nullptr;uintptr_t orgTGLPanelBacklight=0;
 static uint32_t wrapTGLPanelBacklight(void*,uint32_t);
 void install(KernelPatcher &patcher,unsigned index,uintptr_t address,size_t size){INSTALL}
};
XE *XE::callbackXE=nullptr;
BODY
alignas(8) uint8_t controller[0x1600]{};
uint32_t period=0,seen=0,applied=0,result=0x12345678;unsigned calls=0;
bool initialize=false;
void setPeriod(uint32_t value){period=value;memcpy(controller+0xe60,&value,4);}
uint32_t native(void *object,uint32_t brightness) {
 ++calls;seen=brightness;
 if(object==controller && initialize){setPeriod(480);initialize=false;}
 if(object==controller && period && brightness<=65535)applied=uint32_t(period*brightness)/65535;
 return result;
}
int main() {
 XE xe;XE::callbackXE=&xe;xe.tglObservationController=controller;xe.orgTGLPanelBacklight=(uintptr_t)native;
 // Native startup is allowed to initialize its own period; no port/power
 // binding, MMIO reader or alternate LightUp routine exists in this fixture.
 initialize=true;setPeriod(0);calls=0;
 assert(XE::wrapTGLPanelBacklight(controller,0)==result && calls==1 && seen==0 && period==480);
 assert(XE::wrapTGLPanelBacklight(controller,0)==result && seen==771 && applied==5);
 for(auto p:{1U,480U,1000U,65535U,65536U,120000U,24000000U,0xfffffffeU}) {
  setPeriod(p);calls=0;assert(XE::wrapTGLPanelBacklight(controller,0)==result && calls==1 && applied>=1);
  assert(seen>=771 && uint64_t(p)*seen>=65535);
  const auto floor=seen;
  for(auto brightness:{floor,32768U,65535U})if(brightness>=floor) {
   assert(XE::wrapTGLPanelBacklight(controller,brightness)==result && seen>=brightness);
  }
 }
 // Realistic native period: the low 1..5% steps above the first duty retain
 // distinct increasing duties above the visible floor.
 setPeriod(17777);assert(XE::wrapTGLPanelBacklight(controller,0)==result && seen==771 && applied==209);
 assert(TGLBacklight::minimumRequest(0,17777,0)==4);
 assert(TGLBacklight::minimumRequest(0,17777,255)==64*257);
 uint32_t last=0;
 for(uint32_t b=0;b<=65535;++b) {
  const auto request=TGLBacklight::minimumRequest(b,17777,3);
  assert(request>=771 && request<=65535 && request>=last);last=request;
 }
 assert(last==65535);
 setPeriod(480);unsigned previous=0;
 for(unsigned level:{655U,1311U,1966U,2621U,3277U}) {
  assert(XE::wrapTGLPanelBacklight(controller,level)==result && seen>=level && applied>previous);previous=applied;
 }
 for(auto p:{0U,~0U}) {setPeriod(p);calls=0;assert(XE::wrapTGLPanelBacklight(controller,0)==result && seen==0 && calls==1);}
 setPeriod(480);assert(XE::wrapTGLPanelBacklight(controller,65536)==result && seen==65536);
 assert(XE::wrapTGLPanelBacklight(controller,~0U)==result && seen==~0U);
 for(unsigned excluded=0;excluded<6;++excluded) {
  XE foreign;XE::callbackXE=&foreign;foreign.orgTGLPanelBacklight=(uintptr_t)native;foreign.tglObservationController=controller;
  void *object=controller;
  if(excluded==0)foreign.tglActive=false;if(excluded==1)foreign.adlsDisplaySelected=true;
  if(excluded==2)foreign.display13FramebufferRequested=true;if(excluded==3)foreign.xeProfile.family=XELP::Family::AlderLakeS;
  if(excluded==4)foreign.tglObservationController=nullptr;if(excluded==5)object=nullptr;
  calls=0;assert(XE::wrapTGLPanelBacklight(object,0)==result && calls==1 && seen==0);
 }
 XE::callbackXE=&xe;
 const uint8_t entry[]={0x55,0x48,0x89,0xe5,0x41,0x56,0x53,0x48,0xff,0x05,0x90,0x44,0x09,0x00};
 for(unsigned bad=0;bad<8;++bad) {
  std::vector<uint8_t> image(0x50000);memcpy(image.data()+0x4a56a,entry,sizeof(entry));
  XE instance;KernelPatcher patcher;auto size=image.size();
  if(bad==1)size=0x4a56a+sizeof(entry)-1;
  if(bad==2)patcher.delta=1;if(bad==3)image[0x4a56a]^=1;if(bad==4)instance.tglActive=false;
  if(bad==5)instance.adlsDisplaySelected=true;if(bad==6)instance.display13FramebufferRequested=true;
  if(bad==7)instance.xeProfile.family=XELP::Family::AlderLakeS;
  const auto before=image;instance.install(patcher,0,(uintptr_t)image.data(),size);
  assert(patcher.routes==(bad==0?1U:0U) && image==before);
 }
 puts("PASS native TGL brightness minimum: always-forward cold startup, visible minimum duty, native low range, exact short-route qualification and foreign/invalid passthrough");
}
'''.replace('BODY',body).replace('INSTALL',install)
# No long route or PWM-enable patch API is supplied to the fixture.
with tempfile.TemporaryDirectory(prefix='tgl-backlight-') as d:
 p=Path(d);(p/'test.cpp').write_text(code)
 subprocess.run(['clang++','-std=c++17','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(root/'WhateverXe'),str(p/'test.cpp'),'-o',str(p/'check')],check=True)
 subprocess.run([str(p/'check')],check=True)

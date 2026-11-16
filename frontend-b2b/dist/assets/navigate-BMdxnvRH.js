function o(t){const n=t.startsWith("/")?t:"/"+t;window.history.pushState({},"",n),window.dispatchEvent(new PopStateEvent("popstate"))}export{o as n};

(function() {
  function sendBlob(blob) {
    const reader = new FileReader();
    reader.onloadend = function() {
      window.postMessage({ type: 'PDF_URL_INTERCEPTED', base64: reader.result }, '*');
    };
    reader.readAsDataURL(blob);
  }

  // 1. Hook window.open (Prevents new tab)
  const origOpen = window.open;
  window.open = function(url, target, features) {
    if (typeof url === 'string') {
      if (url.startsWith('blob:')) {
        fetch(url).then(res => res.blob()).then(sendBlob);
      } else {
        window.postMessage({ type: 'PDF_URL_FOUND', url: url }, '*');
      }
    }
    return null; // Stop the new tab from opening!
  };

  // 2. Hook URL.createObjectURL
  const origCreateObj = URL.createObjectURL;
  URL.createObjectURL = function(obj) {
    if (obj instanceof Blob && (obj.type === 'application/pdf' || obj.type.includes('pdf'))) {
      sendBlob(obj);
    }
    return origCreateObj.apply(this, arguments);
  };

  // 3. Hook anchor click()
  const origClick = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function() {
    if (this.href && this.target === '_blank') {
       // It's a normal link opening in a new tab
       window.postMessage({ type: 'PDF_URL_FOUND', url: this.href }, '*');
       return;
    }
    if (this.download && this.href && this.href.startsWith('blob:')) {
      fetch(this.href).then(res => res.blob()).then(sendBlob);
      return;
    }
    return origClick.apply(this, arguments);
  };

  // 4. Hook anchor dispatchEvent
  const origDispatchEvent = HTMLAnchorElement.prototype.dispatchEvent;
  HTMLAnchorElement.prototype.dispatchEvent = function(event) {
    if (event.type === 'click' && this.download && this.href && this.href.startsWith('blob:')) {
      fetch(this.href).then(res => res.blob()).then(sendBlob);
      event.stopPropagation();
      return false;
    }
    return origDispatchEvent.apply(this, arguments);
  };
})();

/**
 * Grid Up — İZ C: Arayüz testleri için paylaşılan sahte (mock) DOM ortamı.
 * test_arayuz_sozlesme.mjs ve test_arayuz_kabul.mjs bu modülü kullanır.
 * Gerçek operasyon veritabanına veya canlı API'ye bağlanmaz.
 */

// Basit ve Güvenilir Mock DOM Ortamı
class MockElement {
    constructor(tagName = 'div', id = '') {
        this.tagName = tagName.toUpperCase();
        this._id = id;
        this.className = '';
        this.classList = {
            add: (c) => {
                const parts = this.className ? this.className.split(' ').filter(Boolean) : [];
                if (!parts.includes(c)) parts.push(c);
                this.className = parts.join(' ');
            },
            remove: (c) => {
                const parts = this.className ? this.className.split(' ').filter(Boolean) : [];
                this.className = parts.filter(x => x !== c).join(' ');
            },
            contains: (c) => (this.className ? this.className.split(' ').includes(c) : false)
        };
        this._textContent = undefined;
        this._innerHTML = undefined;
        this.children = [];
        this.parentNode = null;
        this.style = {};
        this.attributes = {};
        this.eventListeners = {};
        this.value = '';
        this.width = 480;
        this.height = 360;
        this.canvasCalls = [];

        if (id && global.document && global.document.registerElement) {
            global.document.registerElement(id, this);
        }
    }

    get id() {
        return this._id;
    }

    set id(val) {
        this._id = val;
        if (val && global.document && global.document.registerElement) {
            global.document.registerElement(val, this);
        }
    }

    get textContent() {
        if (this._textContent !== undefined) return this._textContent;
        return this.children.map(c => c.textContent).join(' ');
    }

    set textContent(val) {
        this._textContent = String(val);
        this._innerHTML = undefined;
        this.children = [];
    }

    get innerHTML() {
        if (this._innerHTML !== undefined) return this._innerHTML;
        if (this._textContent !== undefined) {
            return this._textContent
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }
        return this.children.map(c => c.innerHTML).join('');
    }

    set innerHTML(val) {
        this._innerHTML = String(val);
        if (val === '') {
            this.children = [];
        }
    }

    focus() {}

    appendChild(child) {
        this._textContent = undefined;
        this._innerHTML = undefined;
        child.parentNode = this;
        this.children.push(child);
        return child;
    }

    remove() {
        if (this._id && global.document && global.document.elements) {
            global.document.elements.delete(this._id);
        }
        if (this.parentNode) {
            const idx = this.parentNode.children.indexOf(this);
            if (idx !== -1) {
                this.parentNode.children.splice(idx, 1);
            }
        }
    }

    querySelector(selector) {
        for (const child of this.children) {
            if (selector.startsWith('.') && child.className.split(' ').includes(selector.slice(1))) {
                return child;
            }
            if (selector.startsWith('#') && child.id === selector.slice(1)) {
                return child;
            }
            if (child.tagName.toLowerCase() === selector.toLowerCase()) {
                return child;
            }
            const found = child.querySelector(selector);
            if (found) return found;
        }
        return null;
    }

    querySelectorAll(selector) {
        const results = [];
        for (const child of this.children) {
            if (selector.startsWith('.') && child.className.split(' ').includes(selector.slice(1))) {
                results.push(child);
            } else if (selector.startsWith('#') && child.id === selector.slice(1)) {
                results.push(child);
            } else if (child.tagName.toLowerCase() === selector.toLowerCase()) {
                results.push(child);
            }
            results.push(...child.querySelectorAll(selector));
        }
        return results;
    }

    addEventListener(event, callback) {
        this.eventListeners[event] = this.eventListeners[event] || [];
        this.eventListeners[event].push(callback);
    }

    click() {
        const list = this.eventListeners['click'] || [];
        for (const cb of list) {
            cb({ stopPropagation: () => {} });
        }
    }

    getBoundingClientRect() {
        return { width: this.width, height: this.height, left: 0, top: 0 };
    }

    getContext() {
        return {
            fillRect: (...args) => { this.canvasCalls.push({ type: 'fillRect', args }); },
            clearRect: (...args) => { this.canvasCalls.push({ type: 'clearRect', args }); },
            beginPath: () => { this.canvasCalls.push({ type: 'beginPath' }); },
            arc: (...args) => { this.canvasCalls.push({ type: 'arc', args }); },
            fill: () => { this.canvasCalls.push({ type: 'fill' }); },
            stroke: () => { this.canvasCalls.push({ type: 'stroke' }); },
            moveTo: (x, y) => { this.canvasCalls.push({ type: 'moveTo', x, y }); },
            lineTo: (x, y) => { this.canvasCalls.push({ type: 'lineTo', x, y }); },
            closePath: () => { this.canvasCalls.push({ type: 'closePath' }); },
            fillText: (...args) => { this.canvasCalls.push({ type: 'fillText', args }); },
            save: () => {},
            restore: () => {},
            scale: () => {},
            setLineDash: () => {}
        };
    }

    removeAttribute(name) {
        delete this.attributes[name];
    }
}

class MockDocument {
    constructor() {
        this.elements = new Map();
        this.body = new MockElement('body', 'body');
    }

    createElement(tagName) {
        return new MockElement(tagName);
    }

    getElementById(id) {
        return this.elements.get(id) || null;
    }

    registerElement(id, el) {
        this.elements.set(id, el);
    }

    querySelectorAll(selector) {
        const results = [];
        for (const el of this.elements.values()) {
            if (selector.startsWith('[id^="') && selector.endsWith('"]')) {
                const prefix = selector.slice(6, -2);
                if (el.id.startsWith(prefix)) results.push(el);
            } else if (selector.startsWith('.')) {
                const cls = selector.slice(1);
                if (el.className.split(' ').includes(cls)) results.push(el);
            }
        }
        return results;
    }
}

// Global ortam kurulumu
function setupMockEnvironment() {
    const doc = new MockDocument();

    const ids = [
        'hierarchy-container', 'hierarchy-count',
        'active-module-badge', 'active-module-name', 'active-module-status-badge', 'active-module-device-badge',
        'val-time', 'val-feed', 'val-rssi', 'val-durum-zaman',
        'module-error-banner',
        'val-temp', 'val-hum', 'val-tmax', 'val-l1', 'val-l2', 'val-l3', 'val-notr', 'val-arc',
        'val-tmax-box', 'hotspot-coord', 'current-diff',
        'temp-status', 'hum-status', 'notr-status', 'arc-status',
        'card-temp', 'card-hum', 'card-tmax', 'card-current', 'card-notr', 'card-arc',
        'thermal-source-badge', 'thermal-synthetic-overlay', 'btn-live-thermal', 'btn-toggle-smooth', 'btn-toggle-grid',
        'thermalCanvas', 'hotspot-reticle', 'reticle-temp',
        'thermal-tooltip', 'tooltip-temp', 'tooltip-coord',
        'thermal-status-banner', 'banner-icon', 'banner-title', 'banner-desc',
        'active-alarm-count', 'alarms-container', 'audit-container',
        'operator-id-input',
        'timeseries-metric', 'timeseries-range', 'timeseries-interval', 'btn-refresh-series',
        'timeseriesCanvas', 'timeseries-message', 'timeseries-info', 'timeseries-tooltip',
        'api-status-led', 'api-status-text', 'clock-display'
    ];

    ids.forEach(id => {
        const tagName = id.toLowerCase().includes('canvas') ? 'canvas' : (id.includes('input') ? 'input' : (id.includes('select') ? 'select' : 'div'));
        const el = new MockElement(tagName, id);
        doc.registerElement(id, el);
    });

    // Default operator input value
    doc.getElementById('operator-id-input').value = 'test_operator';

    global.document = doc;
    global.window = {
        location: { hostname: 'localhost', port: '8080', protocol: 'http:' },
        addEventListener: () => {}
    };
    return doc;
}


export { MockElement, MockDocument, setupMockEnvironment };

export async function loadApp() {
    const mod = await import('../app.js');
    return mod.default || globalThis.GridUpApp || mod;
}

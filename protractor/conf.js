exports.config = {
    seleniumAddress: 'http://localhost:4444/wd/hub',
    specs: ['blueprints-spec.js'],
    multiCapabilities: [{
        browserName: 'firefox'
    }, {
        browserName: 'chrome'
    }]
};

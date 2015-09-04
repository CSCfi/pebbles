exports.config = {
    seleniumAddress: 'http://localhost:4444/wd/hub',
    specs: ['blueprints-spec.js'],
    multiCapabilities: [{
        browserName: 'firefox'
    }, {
        browserName: 'chrome'
    }]
};
if (process.env.TRAVIS) {
    exports.config.sauceUser = process.env.SAUCE_USERNAME;
    exports.config.sauceKey = process.env.SAUCE_ACCESS_KEY;
    exports.config.capabilities = {
        'browserName': 'chrome',
        'tunnel-identifier': process.env.TRAVIS_JOB_NUMBER,
        'build': process.env.TRAVIS_BUILD_NUMBER
    };
}

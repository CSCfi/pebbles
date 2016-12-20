config = {
    specs: ['blueprints-spec.js'],
    params: {
        login: {
            user: 'admin@example.org',
            password: 'testpass'
        }
    }
};

if (process.env.TRAVIS) {
    config.sauceUser = process.env.SAUCE_USERNAME;
    config.sauceKey = process.env.SAUCE_ACCESS_KEY;
    config.capabilities = {
        'name': 'Pebbles E2E Tests',
        'browserName': 'chrome',
        'tunnel-identifier': process.env.TRAVIS_JOB_NUMBER,
        'build': process.env.TRAVIS_BUILD_NUMBER
    };
    config.params.baseURL = 'http://localhost:8888/#/';
} else {
    config.params.baseURL = 'http://localhost:8888/#/';
    config.seleniumAddress = 'http://localhost:4444/wd/hub';
}

exports.config = config

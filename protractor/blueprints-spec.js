describe('Pouta Blueprints', function() {
  var testUserName = 'test@example.org';
  var testPassword = 'testpass';

  beforeEach(function() {
    browser.get('http://localhost:8888/#/');
  });

  it('create first user', function() {
    browser.get('http://localhost:8888/#/initialize');
    element(by.model('user.email')).sendKeys(testUserName);
    element(by.model('user.password')).sendKeys(testPassword);
    element(by.model('user.passwordConfirm')).sendKeys(testPassword);
    element(by.buttonText('Create')).click();
  });

  it('should see dashboard as admin', function() {
    element(by.model('email')).sendKeys(testUserName);
    element(by.model('password')).sendKeys(testPassword);
    element(by.css('[value="Sign in"]')).click();
    var title = element.all(by.tagName('h1')).first();
    expect(title.getText()).toBe('Dashboard');
  });

  it('should see user list', function() {
    var navLinks = element.all(by.css('.nav li'));
    expect(navLinks.get(1).getText()).toBe('Users');
    navLinks.get(1).$$('a').click();

    var usersTitle = element.all(by.tagName('h1')).first();
    expect(usersTitle.getText()).toBe('Users');

    var userList = element.all(by.repeater('user in users'));
    expect(userList.count()).toEqual(2);
  });
});

describe('Pebbles', function() {

  beforeEach(function() {
    browser.get(browser.params.baseURL);
  });

  it('should see dashboard as admin', function() {
    element(by.model('email')).sendKeys(browser.params.login.user);
    element(by.model('password')).sendKeys(browser.params.login.password);
    element(by.css('[value="Sign in"]')).click();
    var title = element.all(by.tagName('h1')).first();
    expect(title.getText()).toBe('Environments');
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

  it('can update user quota', function() {
    var navLinks = element.all(by.css('.nav li'));
    expect(navLinks.get(1).getText()).toBe('Users');
    navLinks.get(1).$$('a').click();

    var usersTitle = element.all(by.tagName('h1')).first();
    expect(usersTitle.getText()).toBe('Users');

    var users = element.all(by.repeater('user in users')).$$('td').get(2);
    expect(users.getText()).toEqual("0 / 1");
    element(by.buttonText('Update quotas...')).click();
    element(by.model('addedAmount')).sendKeys("10");
    element(by.buttonText('Set')).click()
    var users2 = element.all(by.repeater('user in users')).$$('td').get(2);
    expect(users2.getText()).toEqual("0 / 10");
  });
});

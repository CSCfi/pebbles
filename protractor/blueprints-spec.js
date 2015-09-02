describe('Pouta Blueprints', function() {
  beforeEach(function() {
    browser.get('https://localhost:8888/#/');
  });

  it('should see dashboard as admin', function() {
    element(by.model('email')).sendKeys('test@example.org');
    element(by.model('password')).sendKeys('testpass');
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

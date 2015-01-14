ResourceCloud.service('AuthService', AuthService = function($q, localStorageService, Session) {
    this.login = function(credentials) {
        var me = this;
        deferred = $q.defer()
        Session.create(credentials, true).then(function(user) {
            me.setToken(credentials);
            return deferred.resolve(user);
        }, function(response) {
            if (response.status == 401) {
                return deferred.reject(false);
            }
            throw new Error("No handler for status code " + response.status);
        });
        return deferred.promise
    };

    this.logout = function() {
        localStorageService.clearAll();
    };
})

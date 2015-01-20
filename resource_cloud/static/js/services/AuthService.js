app.factory('AuthService', ['$q', 'localStorageService', 'Session', function($q, localStorageService, Session) {
    return {
        login : function(email, password) {
            var me = this;
            var deferred = $q.defer();
            var credentials = {'email': email, 'password': password};
            Session.create(credentials, true).then(function(response) {
                me.setToken(response.token);
                me.setAdminStatus(response.is_admin);
                return deferred.resolve(response);
            }, function(response) {
                if (response.status == 401) {
                    return deferred.reject(false);
                }
                throw new Error("No handler for status code " + response.status);
            });
            return deferred.promise;
        },

        logout : function() {
            var deferred = $q.defer();
            localStorageService.clearAll();
            return deferred.promise;
        },

        isAuthenticated : function() {
            var token = this.getToken();
            if (token) {
                return true;
            }
            localStorageService.clearAll();
            return false;
        },
        
        isAdmin : function() {
            var adminStatus = this.getAdminStatus();
            if (adminStatus == "true") {
                return true;
            }
            return false;
        },

        setToken : function(token) {
            localStorageService.set('token', btoa(token + ":"));
        },

        getToken : function() {
            return localStorageService.get('token');
        },

        setAdminStatus : function(isAdmin) {
            localStorageService.set('isAdmin', isAdmin);
        },

        getAdminStatus : function() {
            return localStorageService.get('isAdmin');
        }
    }
}]);


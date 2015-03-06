app.factory('AuthService', ['$q', 'localStorageService', 'Session', 'Restangular',
                    function($q,   localStorageService,   Session,   Restangular) {
    return {
        login : function(email, password) {
            var me = this;
            var deferred = $q.defer();
            var credentials = {'email': email, 'password': password};
            Session.create(credentials, true).then(function(response) {
                me.setToken(response.token);
                me.setAdminStatus(response.is_admin);
                me.setUserId(response.user_id);
                return deferred.resolve(response);
            }, function(response) {
                if (response.status === 401) {
                    return deferred.reject(false);
                }
                throw new Error("No handler for status code " + response.status);
            });
            return deferred.promise;
        },

        logout : function() {
            localStorageService.clearAll();
        },

        isAuthenticated : function() {
            var token = this.getToken();
            if (token) {
                return true;
            }
            localStorageService.clearAll();
            return false;
        },

        changePasswordWithToken : function(token_id, password) {
            return $q(function(resolve, reject) {
                var token = Restangular.one('activations', token_id);
                token.customPOST({password: password}).then(function(response) {
                    resolve({status: response.status});
                }, function(response) {
                    console.log("Changing password caused an exception, HTTP Error code " + response.status);
                    reject({status: response.status});
                });
            });
        },

        isAdmin : function() {
            var adminStatus = this.getAdminStatus();
            if (adminStatus === "true") {
                return true;
            }
            return false;
        },

        setUserId : function(userId) {
            localStorageService.set('userId', userId);
        },

        getUserId : function() {
            return localStorageService.get('userId');
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
    };
}]);


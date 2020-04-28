app.factory('AuthService', ['$q', 'localStorageService', 'Session', 'Restangular',
                    function($q,   localStorageService,   Session,   Restangular) {
    return {
        login : function(eppn, password) {
            var me = this;
            var deferred = $q.defer();
            var credentials = {'eppn': eppn, 'password': password};
            Session.create(credentials, true).then(function(response) {
                me.setToken(response.token);
                me.setUserName(eppn);
                me.setAdminStatus(response.is_admin);
                me.setWorkspaceOwnerStatus(response.is_workspace_owner);
                me.setWorkspaceManagerStatus(response.is_workspace_manager);
                me.setUserId(response.user_id);
                me.setIcons(response.icon_value);
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
                $('body').removeClass('loginPage').addClass('');
                return true;
            }
            localStorageService.clearAll();
            $('body').removeClass('loginPage').addClass('loginPage');
            return false;
        },

        isNotAuthenticated : function() {
            return ! this.isAuthenticated();
        },

        changePasswordWithToken : function(token_id, password) {
            return $q(function(resolve, reject) {
                var token = Restangular.one('activations', token_id);
                token.customPOST({password: password}).then(function(response) {
                    resolve({status: response.status, eppn: response.eppn});
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

        isWorkspaceOwnerOrAdmin : function() {
            var workspaceOwnerStatus = this.getWorkspaceOwnerStatus();
            var adminStatus = this.getAdminStatus();
            if (workspaceOwnerStatus === "true" || adminStatus === "true") {
                return true;
            }
            return false;
        },

        isWorkspaceManagerOrAdmin : function() {
            var workspaceManagerStatus = this.getWorkspaceManagerStatus();
            var workspaceOwnerStatus = this.getWorkspaceOwnerStatus();
            var adminStatus = this.getAdminStatus();
            if (workspaceManagerStatus === "true" || workspaceOwnerStatus === "true" || adminStatus === "true") {
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
        
        setUserName : function(userName) {
            localStorageService.set('userName', userName);
        },

        getUserName : function() {
            return localStorageService.get('userName');
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
        },

        setWorkspaceOwnerStatus : function(isWorkspaceOwner) {
            localStorageService.set('isWorkspaceOwner', isWorkspaceOwner);
        },


        getWorkspaceOwnerStatus : function() {
            return localStorageService.get('isWorkspaceOwner');
        },

        setWorkspaceManagerStatus : function(isWorkspaceManager) {
            localStorageService.set('isWorkspaceManager', isWorkspaceManager);
        },

        getWorkspaceManagerStatus : function() {
            return localStorageService.get('isWorkspaceManager');
        },

        setIcons : function(iconValue) {
            localStorageService.set('iconValue', iconValue);
        },

        getIcons : function() {
            return localStorageService.get('iconValue');
        },


    };
}]);


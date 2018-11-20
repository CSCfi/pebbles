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
                me.setGroupOwnerStatus(response.is_group_owner);
                me.setGroupManagerStatus(response.is_group_manager);
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
                    resolve({status: response.status, email: response.email});
                }, function(response) {
                    console.log("Changing password caused an exception, HTTP Error code " + response.status);
                    reject({status: response.status});
                });
            });
        },

        isAdmin : function() {
            var adminStatus = this.getAdminStatus();
            var isUserRoleForced = this.getUserRoleForcedStatus();
            if (isUserRoleForced === "true"){
                return false;
            }
            if (adminStatus === "true") {
                return true;
            }
            return false;
        },

        isGroupOwnerOrAdmin : function() {
            var groupOwnerStatus = this.getGroupOwnerStatus();
            var adminStatus = this.getAdminStatus();
            var isUserRoleForced = this.getUserRoleForcedStatus();
            if (isUserRoleForced === "true"){
                return false;
            }
            if (groupOwnerStatus === "true" || adminStatus === "true") {
                return true;
            }
            return false;
        },

        isGroupManagerOrAdmin : function() {
            var groupManagerStatus = this.getGroupManagerStatus();
            var groupOwnerStatus = this.getGroupOwnerStatus();
            var adminStatus = this.getAdminStatus();
            var isUserRoleForced = this.getUserRoleForcedStatus();
            if (isUserRoleForced === "true"){
                return false;
            }
            if (groupManagerStatus === "true" || groupOwnerStatus === "true" || adminStatus === "true") {
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

        setGroupOwnerStatus : function(isGroupOwner) {
            localStorageService.set('isGroupOwner', isGroupOwner);
        },


        getGroupOwnerStatus : function() {
            return localStorageService.get('isGroupOwner');
        },

        setGroupManagerStatus : function(isGroupManager) {
            localStorageService.set('isGroupManager', isGroupManager);
        },

        getGroupManagerStatus : function() {
            return localStorageService.get('isGroupManager');
        },

        setIcons : function(iconValue) {
            localStorageService.set('iconValue', iconValue);
        },

        getIcons : function() {
            return localStorageService.get('iconValue');
        },


        setUserRoleForcedStatus : function(isUserRoleForced) {
            localStorageService.set('isUserRoleForced', isUserRoleForced);
        },

        getUserRoleForcedStatus : function() {
            return localStorageService.get('isUserRoleForced');
        }
    };
}]);


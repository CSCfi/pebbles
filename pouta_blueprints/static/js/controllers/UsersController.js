app.controller('UsersController', ['$q', '$scope', '$interval', 'AuthService', 'Restangular',
                          function ($q,   $scope,   $interval,   AuthService,   Restangular) {
        Restangular.setDefaultHeaders({token: AuthService.getToken()});
        $scope.include_deleted = false;
        $scope.includeRow = function(value, index) {
            if ($scope.include_deleted) {
                return true;
            } else {
                return !value.is_deleted;
            }
        };

        if (AuthService.isAdmin()) {
            var users = Restangular.all('users');
            var quota = Restangular.all('quota');

            users.getList().then(function (response) {
                $scope.users = response;
            });

            $scope.new_user = '';
            $scope.add_user = function(email) {
                var user_parameters = {email: email};
                if (email) {
                    users.post(user_parameters).then(function() {
                        users.getList().then(function (response) {
                            $scope.users = response;
                        });
                    });
                }
            };

            $scope.remove_user = function(user) {
                user.remove().then(function () {
                    users.getList().then(function (response) {
                        $scope.users = response;
                    });
                });
            };

            $scope.invite_users = function() {
                var params = {addresses: $scope.invitedUsers};
                users.patch(params).then(function(response) {
                    users.getList().then(function (response) {
                        $scope.users = response;
                    });
                });
            };

            $scope.increase_quota = function(amount, user) {
                var resource = quota;
                if (user) {
                    resource = resource.one(user.id);
                }
                resource.customPUT({type: 'relative', value: amount}).then(function() {
                    users.getList().then(function(response) {
                        $scope.users = response;
                    });
                });
            };

            $scope.set_quota = function(amount, user) {
                var resource = quota;
                if (user) {
                    resource = resource.one(user.id);
                }
                resource.customPUT({type: 'absolute', value: amount}).then(function() {
                    users.getList().then(function(response) {
                        $scope.users = response;
                    });
                });

            };
        }
    }]);


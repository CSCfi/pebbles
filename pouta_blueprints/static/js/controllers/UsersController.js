app.controller('UsersController', ['$q', '$scope', '$interval', 'AuthService', 'Restangular',
                          function ($q,   $scope,   $interval,   AuthService,   Restangular) {
        Restangular.setDefaultHeaders({token: AuthService.getToken()});

        if (AuthService.isAdmin()) {
            var users = Restangular.all('users');
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
        }
    }]);


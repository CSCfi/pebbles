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
                    users.post(user_parameters).then(function (response) {
                        $scope.users.push(response);
                    });
                }
            }

            $scope.remove_user = function(user) {
                user.remove().then(function () {
                    var index = $scope.users.indexOf(user);
                    if (index > -1) $scope.users.splice(index, 1);
                });
            }

            $scope.invite_users = function() {
                console.log("invite users:");
                console.log($scope.invitedUsers);
                var params = {addresses: $scope.invitedUsers};
                users.patch(params).then(function(response) {
                    $scope.users = response;
                });
            }
        }
    }]);


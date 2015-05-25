app.controller('UsersController', ['$q', '$scope', '$interval', '$modal', '$filter', 'AuthService', 'Restangular',
                          function ($q,   $scope,   $interval,   $modal,   $filter,   AuthService,   Restangular) {
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

            $scope.open_quota_dialog = function(users) {
                var modalQuota = $modal.open({
                    templateUrl: '/partials/modal_quota.html',
                    controller: 'ModalQuotaController',
                    resolve: {
                        users: function() {
                            return $filter('filter')(users, function(value, index) {
                                return !value.is_deleted;
                            });
                        }
                    }
                });
                modalQuota.result.then(function (changed) {
                    if (changed) {
                        $scope.users.getList().then(function (response) {
                            $scope.users = response;
                        });
                    }
                });
            };
        }
    }]);

app.controller('ModalQuotaController', function ($q, $scope, $modalInstance, Restangular, users) {
    $scope.users = users;

    var change_quota = function(amount, change) {
        var promises = [];
        var quota = Restangular.all('quota');

        for (var i = 0; i < users.length; i++) {
            var user = users[i];
            var resource = quota.one(user.id);
            promises.push(resource.customPUT({type: change, value: amount}));
        }

        if (users.length === 0) {
            promises.push(quota.customPUT({type: change, value: amount}));
        }

        return $q.all(promises);
    };

    $scope.increase_quota = function(amount) {
        if (amount !== undefined) {
            change_quota(amount, 'relative').then(function() {
                $modalInstance.close(true);
            });
        }
    };

    $scope.set_quota = function(amount) {
        if (amount !== undefined) {
            change_quota(amount, 'absolute').then(function() {
                $modalInstance.close(true);
            });
        }
    };

    $scope.cancel = function() {
        $modalInstance.dismiss('cancel');
    };

});


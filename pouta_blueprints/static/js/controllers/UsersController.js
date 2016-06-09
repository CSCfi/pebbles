app.controller('UsersController', ['$q', '$scope', '$interval', '$uibModal', '$filter', 'AuthService', 'Restangular',
                          function ($q,   $scope,   $interval,   $uibModal,   $filter,   AuthService,   Restangular) {
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

            quota.getList().then(function (response) {
                $scope.credits_spent = [];
                angular.forEach(response, function(value, key) {
                    $scope.credits_spent[value.id] = value.credits_spent;
                });
                $scope.quotas = response;
            });

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

            $scope.block_user = function(user) {
                var block = !user.is_blocked
                var user_blacklist = Restangular.one('users', user.id).all('user_blacklist').customPUT({'block': block});
                user_blacklist.then(function () {
                    users.getList().then(function (response) {
                        $scope.users = response;
                    });
                });

            };

            $scope.get_activation_url = function(user) {
                $uibModal.open({
                    size: 'lg',
                    templateUrl: '/partials/modal_activation_url.html',
                    controller: 'ModalActivationUrlController',
                    resolve: {
                       user: user
                    }
                });
            };

            $scope.open_quota_dialog = function(users) {
                var modalQuota = $uibModal.open({
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

            $scope.open_invite_users_dialog = function() {
                var modalInviteUsers = $uibModal.open({
                    templateUrl: '/partials/modal_invite.html',
                    controller: 'ModalInviteUsersController',
                    resolve: {
                        users: function() {
                            return $scope.users;
                        }
                    }
                });
                modalInviteUsers.result.then(function() {
                    $scope.users.getList().then(function (response) {
                        $scope.users = response;
                    });
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

app.controller('ModalActivationUrlController', function($scope, $modalInstance, Restangular, user) {

    var users = Restangular.one('users', user.id);
    var user_activation_url = users.customGET('user_activation_url');
    user_activation_url.then(function (response) {
            $scope.activation_url = response['activation_url'];
        });


    $scope.cancel = function() {
        $modalInstance.dismiss('cancel');
    };
});

app.controller('ModalInviteUsersController', function($scope, $modalInstance, users) {
    $scope.invite_users = function(invitedUsers) {
        var params = {addresses: invitedUsers};
        users.patch(params).then(function() {
            $modalInstance.close(true);
        });
    };

    $scope.cancel = function() {
        $modalInstance.dismiss('cancel');
    };
});

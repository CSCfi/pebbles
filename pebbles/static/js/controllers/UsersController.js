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

            $scope.users = []

            $scope.userTypes = ['All', 'Admins', 'Group Owners', 'Inactive', 'Active', 'Blocked']
            var defaultUserType = 'All';
            $scope.selectedUserType = defaultUserType;

            $scope.visiblePages = 4;  // Visible number of pages in the pagination
            $scope.currentPage = 1;  // Starting page
            var itemsPerPage = 50;
            $scope.itemsPerPage = itemsPerPage;


            var users_fetch = function(user_type, page, page_size, filter_str){
                users.getList({
                    filter_str: filter_str,  // optional
                    user_type: user_type,
                    page: page,
                    page_size: page_size
                }).then(function (response) {
                    $scope.users = response;
                });
            };

            var users_count = function(user_type, filter_str) {
                users.patch({
                    user_type: user_type,
                    filter_str: filter_str,  // optional
                    count: true
                }).then(function(response) {
                    $scope.totalUsers = response;  // Used by the pagination to determine the total number of pages
                });
            };

            users_count(defaultUserType);
            users_fetch(defaultUserType, 0, itemsPerPage);

            $scope.loadPage = function() {
                // Also consider the query string for filtering users (if given)
                users_fetch($scope.selectedUserType, $scope.currentPage-1, $scope.itemsPerPage, $scope.filter_str);
            };

            $scope.changePageSize = function() {
                $scope.loadPage();
            };

            /* Shows selected user type from the dropdown ($scope.selectedUserType),
               Also considers the query string for filtering users (if given)
            */ 
            $scope.showSelectedUsers = function() {
                 $scope.currentPage = 1;
                 users_count($scope.selectedUserType, $scope.filter_str);
                 $scope.loadPage();
            };

            /* Filter the users based on query string ($scope.filter_str)
               Reset the default user type to 'All' for fetching global results
            */
            $scope.filterUsers = function() {
                $scope.selectedUserType = defaultUserType;
                $scope.showSelectedUsers();
            };

            $scope.new_user = '';
            $scope.add_user = function(email) {
                if ($scope.add_user_form.$valid){
                    var user_parameters = {eppn: email};
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

            $scope.make_group_owner = function(user) {
                var make_group_owner = !user.is_group_owner
                var user_group_owner = Restangular.one('users', user.id).all('user_group_owner').customPUT({'make_group_owner': make_group_owner});
                user_group_owner.then(function () {
                    users.getList().then(function (response) {
                        $scope.users = response;
                    });
                });

            };

            $scope.get_activation_url = function(user) {
                $uibModal.open({
                    size: 'lg',
                    templateUrl: '/partials/modal_url.html',
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

    $scope.url_type = "Activation Link" + ' : ' + user.eppn;
    var users = Restangular.one('users', user.id);
    var user_activation_url = users.customGET('user_activation_url');
    user_activation_url.then(function (response) {
            $scope.url = response['activation_url'];
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
        }, function(response) {
                incorrect_addresses_array = response.data;
                incorrect_addresses = incorrect_addresses_array.join('<br>');
                $.notify({
                     title: 'HTTP ' + response.status,
                     message: '<b>The following emails could not be added:</b> <br>' + incorrect_addresses
                     },
                     {
                         type: 'warning',
                         delay: 8000
                     });
            $modalInstance.close(true);
        });
    };

    $scope.cancel = function() {
        $modalInstance.dismiss('cancel');
    };
});

app.controller('GroupsController', ['$q', '$scope', '$interval', '$uibModal', '$filter', 'AuthService', 'Restangular',
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
            var groups = Restangular.all('groups');

            users.getList().then(function (response) {
                $scope.users = response;
            });

            groups.getList().then(function (response) {
                $scope.groups = response;
            });

            var groupsSF = {};
            groupsSF.schema = {
                "type": "object",
                "title": "Comment",
                "properties": {
                    "name":  {
                    "title": "Group Name",
                    "type": "string",
                    "default": "mygroup"
                    },
                "join_code":  {
                    "title": "Joining Code",
                    "type": "string",
                    "description": "The code/password to join your group",
                    "default": "mycode"
                    },
                "description": {
                    "title": "Group Description",
                    "type": "string",
                    "maxLength": 250,
                    "validationMessage": "Maximum text limit for the description reached!"
                    }
                },
                "required": ["name","join_code"]

            }
            groupsSF.form = [
                "name",
                "join_code",
                {
                    "key": "description",
                    "type": "textarea",
                    "placeholder": "Details of the group"
                }
            ]
            //$scope.groupsSF = groupsSF;

            $scope.openCreateGroupDialog=function() {
                $uibModal.open({
                    templateUrl: '/partials/modal_create_group.html',
                    controller: 'ModalCreateGroupController',
                    size: 'md',
                    resolve: {
                        groupsSF: function() {
                            return groupsSF;
                        },
                        groups: function() {
                            return groups;
                        },
                        users: function() {
                            return $scope.users;
                        }
                    }
                }).result.then(function() {
                     groups.getList().then(function (response) {
                         $scope.groups = response;
                      });
                });
            };

            $scope.openModifyGroupDialog=function(group) {
                $uibModal.open({
                    templateUrl: '/partials/modal_modify_group.html',
                    controller: 'ModalModifyGroupController',
                    size: 'md',
                    resolve: {
                        groupsSF: function() {
                            return groupsSF;
                        },
                        group: function() {
                            return group;
                        },
                        users: function() {
                            return $scope.users;
                        },
                    }
                }).result.then(function() {
                    groups.getList().then(function (response) {
                        $scope.groups = response;
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
        }
    }]);

app.controller('ModalCreateGroupController', function($scope, $modalInstance, groupsSF, groups, users) {

    $scope.groupsSF = groupsSF;
    groupsSF.model = {}
    $scope.userData = users;
    $scope.user_config = {"userModel": [], "banUserModel": [], "ownerModel": []}
    $scope.userSettings = {displayProp: 'email', scrollable: true, enableSearch: true};

    $scope.createGroup = function(form, model, user_config) {
     if (form.$valid) {
            //usersModel_ids = _.map(usersModel, function(item){ return item['id']; });
            groups.post({ 
                 name: model.name, join_code: model.join_code, description: model.description,
                 user_config:{
                     "users": user_config.userModel,
                     "banned_users": user_config.banUserModel,
                     "owners": user_config.ownerModel
                 }
            }).then(function () {
                $modalInstance.close(true);
            }, function(response) {
                $.notify({title: 'HTTP ' + response.status, message: 'unable to create group'}, {type: 'danger'});
            });
        }
    };

    $scope.cancel = function() {
        $modalInstance.dismiss('cancel');
    };
});

app.controller('ModalModifyGroupController', function($scope, $modalInstance, groupsSF, group, users) {

    $scope.groupsSF = groupsSF
    $scope.group = group;
    $scope.userData = users;
    $scope.userSettings = {displayProp: 'email', scrollable: true, enableSearch: true};

    $scope.modifyGroup = function(form, model, user_config) {
     if (form.$valid) {
            $scope.group.name = model.name
            $scope.group.join_code = model.join_code
            $scope.group.description = model.description
            $scope.group.user_config = {
                 "users": user_config.users,
                 "banned_users": user_config.banned_users,
                 "owners": user_config.owners
            }
            $scope.group.put().then(function () {
                $modalInstance.close(true);
            }, function(response) {
                $.notify({title: 'HTTP ' + response.status, message: 'unable to modify group'}, {type: 'danger'});
            });
        }
    };

    $scope.cancel = function() {
        $modalInstance.dismiss('cancel');
    };
});


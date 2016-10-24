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

        if (AuthService.isGroupOwnerOrAdmin()) {
            var groups = Restangular.all('groups');
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
                    "maxLength": 32,
                    "pattern": "^(?!(?:SYSTEM|System|system)).+",  // No case sensitive flag in schemaform
                    "validationMessage": "Required Field! Max length 32 chars",
                    "default": "mygroup"
                    },
                "description": {
                    "title": "Group Description",
                    "type": "string",
                    "maxLength": 250,
                    "validationMessage": "Maximum text limit for the description reached!"
                    }
                },
                "required": ["name"]

            }
            groupsSF.form = [
                "name",
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
                        group_users: function() {
                            var group_users = Restangular.all('groups').one(group.id).all('users');
                            return group_users;
                        }
                    }
                }).result.then(function() {
                    groups.getList().then(function (response) {
                        $scope.groups = response;
                     });
                });
            };

        }
    }]);

app.controller('ModalCreateGroupController', function($scope, $modalInstance, groupsSF, groups) {

    $scope.groupsSF = groupsSF;
    groupsSF.model = {}

    $scope.createGroup = function(form, model) {
     if (form.$valid) {
            groups.post({ 
                 name: model.name, description: model.description,
            }).then(function () {
                $modalInstance.close(true);
            }, function(response) {
                error_message = 'unable to create group'
                if ('name' in response.data){
                    error_message = response.data.name
                }
                $.notify({title: 'HTTP ' + response.status, message: error_message}, {type: 'danger'});
            });
        }
    };

    $scope.cancel = function() {
        $modalInstance.dismiss('cancel');
    };
});

app.controller('ModalModifyGroupController', function($scope, $modalInstance, groupsSF, group, group_users) {

    $scope.groupsSF = groupsSF
    $scope.group = group;
    group_users.getList({'banned_list': true}).then(function (response) {
        $scope.userData = response;
    });
    group_users.getList().then(function (response) {
        $scope.managerData = response;
    });
    $scope.userSettings = {displayProp: 'email', scrollable: true, enableSearch: true};
    var old_name = group.name;

    $scope.modifyGroup = function(form, model, user_config) {
     if (form.$valid) {
            $scope.group.name = model.name
            $scope.group.description = model.description
            $scope.group.user_config = {
                 "banned_users": user_config.banned_users,
                 "managers": user_config.managers
            }
            $scope.group.put().then(function () {
                $modalInstance.close(true);
            }, function(response) {
                error_message = 'unable to create group';
                if ('name' in response.data){
                    error_message = response.data.name;
                    $scope.group.name = old_name;
                }
                if ('error' in response.data){
                    error_message = response.data.error;
                }
                $.notify({title: 'HTTP ' + response.status, message: error_message}, {type: 'danger'});
            });
        }
    };

    $scope.cancel = function() {
        $modalInstance.dismiss('cancel');
    };
});


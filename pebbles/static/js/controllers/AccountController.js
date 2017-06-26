app.controller('AccountController', ['$q', '$scope', '$timeout', 'AuthService', '$upload', 'Restangular', '$uibModal',
                             function($q,   $scope,   $timeout,   AuthService,   $upload,   Restangular,    $uibModal) {
    var user = Restangular.one('users', AuthService.getUserId());
    var quota = Restangular.one('quota', AuthService.getUserId());
    var group_join = Restangular.all('groups').one('group_join');

    var key = null;
    var key_url = null;
    var change_password_result = "";
    var upload_ok = null;

    $scope.getUserName = AuthService.getUserName;

    $scope.isAdmin = function() {
        return AuthService.isAdmin();
    };

    $scope.isGroupManagerOrAdmin = function() {
        return AuthService.isGroupManagerOrAdmin();
    };

    quota.get().then(function (response) {
                $scope.credits_spent = response.credits_spent;
                $scope.credits_quota = response.credits_quota;
            });

    $scope.upload_error = function() {
        if (upload_ok === false) {
            return true;
        }
        return false;
    };

    $scope.upload_success = function () {
        if (upload_ok) {
            return true;
        }
        return false;
    };

    $scope.$watch('files', function () {
        $scope.upload($scope.files);
    });

    $scope.upload = function (files) {
        if (files && files.length) {
            upload_ok = null;
            angular.forEach(files, function(file) {
                $upload.upload({
                    url: '/api/v1/users/'+user.id+'/keypairs/upload',
                    fields: {'username': $scope.username},
                    headers: {'Authorization': 'Basic ' + AuthService.getToken()},
                    file: file
                }).success(function () {
                    upload_ok = true;
                }).error(function() {
                    upload_ok = false;
                });
            });
        }
    };

    $scope.key_url = function() {
        return key_url;
    };

    $scope.key_downloadable = function() {
        if (key) {
            return true;
        }
        return false;
    };

    $scope.generate_key = function() {
        key = null;
        user.post('keypairs/create').then(function(response) {
            key = response.private_key;
            key_url = window.URL.createObjectURL(new Blob([key], {type: "application/octet-stream"}));
        });
    };

    var group_list_exit = Restangular.all('groups').all('group_list_exit');
    var refresh_group_list_exit = function(){
        group_list_exit.getList().then(function (response) {
            $scope.group_list_exit = response;
        });
    };

    refresh_group_list_exit();

    $scope.exit_group = function(group) {
        var group_exit = Restangular.all('groups').one('group_exit').one(group.id);
        group_exit.put().then(function () {
               refresh_group_list_exit();
            }, function(response) {
                $.notify({title: 'HTTP ' + response.status, message: response.data.error}, {type: 'danger'});
            });

     };

    $scope.change_password_msg_visible = function() {
        if (change_password_result === "") {
            return false;
        }
        return true;
    };

    $scope.change_password_msg = function() {
        return change_password_result;
    };

    $scope.update_password = function() {
        user.password = $scope.user.password;
        user.put().then(function() {
            change_password_result = "Password changed";
        }, function(response) {
            var deferred = $q.defer();
            if (response.status === 422) {
                change_password_result = response.data.password.join(', ');
                return deferred.reject(false);
            } else {
                throw new Error("No handler for status code " + response.status);
            }
        });
        $timeout(function() {
            change_password_result = "";
        }, 10000);
    };

    $scope.openGroupJoinModal=function() {
         $uibModal.open({
         templateUrl: '/partials/modal_group_join.html',
         controller: 'ModalGroupJoinController',
         size: 'sm',
         resolve: {
             group_join: function() {
                 return group_join;
             }
         }
         }).result.then(function() {
                 refresh_group_list_exit();
             });
     };
}]);

app.controller('ModalGroupJoinController', function($scope, $modalInstance, group_join) {

    var grp_join_sf = {}
    grp_join_sf.schema = {
            "type": "object",
            "title": "Comment",
            "properties": {
            "join_code":  {
                "title": "Joining Code",
                "type": "string",
                "description": "The code/password to join your group"
                }
            },
            "required": ["join_code"]

        }
    grp_join_sf.form = [
            {"key": "join_code", "type": "textfield", "placeholder": "paste the joining code here"}
        ]
    grp_join_sf.model = {}
    $scope.grp_join_sf = grp_join_sf;
    $scope.group_join = group_join;

    $scope.joinGroup = function(form, model) {
     if (form.$valid) {
            $scope.group_join.one(model.join_code).customPUT().then(function () {
                $.notify({title: 'Success! ', message: 'Group Joined'}, {type: 'success'});
                $modalInstance.close(true);
            }, function(response) {
                $.notify({title: 'HTTP ' + response.status, message: response.data.error}, {type: 'danger'});
            });
        }
    };

    $scope.cancel = function() {
        $modalInstance.dismiss('cancel');
    };
});

app.controller('AccountController', ['$scope', '$timeout', 'AuthService', '$upload', 'Restangular',
                             function($scope,   $timeout,   AuthService,   $upload,   Restangular) {
    var user = Restangular.one('users', AuthService.getUserId());
    var key = null;
    var key_url = null;
    var change_password_result = ""
    var upload_ok = null;

    $scope.upload_error = function() {
        if (upload_ok == false) {
            return true;
        }
        return false;
    }

    $scope.upload_success = function () {
        if (upload_ok) {
            return true;
        }
        return false;
    }

    $scope.$watch('files', function () {
        $scope.upload($scope.files);
    });

    $scope.upload = function (files) {
        if (files && files.length) {
            upload_ok = null;
            for (var i = 0; i < files.length; i++) {
                var file = files[i];
                $upload.upload({
                    url: '/api/v1/users/'+user.id+'/keypairs/upload',
                    fields: {'username': $scope.username},
                    headers: {'Authorization': 'Basic ' + AuthService.getToken()},
                    file: file
                }).success(function (data, status, headers, config) {
                    upload_ok = true;
                }).error(function() {
                    upload_ok = false;
                });
            }
        }
    }

    $scope.key_url = function() {
        return key_url;
    }

    $scope.key_downloadable = function() {
        if (key) {
            return true;
        }
        return false;
    }

    $scope.generate_key = function() {
        key = null;
        user.post('keypairs/create').then(function(response) {
            key = response.private_key;
            key_url = window.URL.createObjectURL(new Blob([key], {type: "application/octet-stream"}));
        });
    }

    $scope.change_password_msg_visible = function() {
        if (change_password_result == "") {
            return false;
        }
        return true;
    }

    $scope.change_password_msg = function() {
        return change_password_result;
    }

    $scope.update_password = function() {
        var params = { password: $scope.user.password };
        user.password = $scope.user.password;
        user.put()
        user.put(params).then(function(response) {
            change_password_result = "Password changed";
        }, function(response) {
            change_password_result = "Unable to change password";
        });
        $timeout(function() {
            change_password_result = "";
        }, 10000)
    }
}]);

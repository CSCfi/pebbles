app.controller('AccountController', ['$q', '$scope', '$timeout', 'AuthService', '$upload', 'Restangular',
                             function($q,   $scope,   $timeout,   AuthService,   $upload,   Restangular) {
    var user = Restangular.one('users', AuthService.getUserId());
    var quota = Restangular.one('quota', AuthService.getUserId());
    var key = null;
    var key_url = null;
    var change_password_result = "";
    var upload_ok = null;

    $scope.getUserName = AuthService.getUserName;

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
}]);

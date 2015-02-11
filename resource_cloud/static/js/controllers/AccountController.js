app.controller('AccountController', ['$scope', '$timeout', 'AuthService', 'Restangular',
                             function($scope,   $timeout,   AuthService,   Restangular) {
    var user = Restangular.one('users', AuthService.getUserId());
    var key = null;
    var key_url = null;
    var change_password_result = ""

    $scope.key_url = function() {
        return key_url;
    }

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
            var deferred = $q.defer();
            if (response.status == 422) {
                activation_success = false;
                change_password_result = response.data.password.join(', ');
                return deferred.reject(false);
            } else {
                throw new Error("No handler for status code " + response.status);
            }
        });
        $timeout(function() {
            change_password_result = "";
        }, 10000)
    };
}]);

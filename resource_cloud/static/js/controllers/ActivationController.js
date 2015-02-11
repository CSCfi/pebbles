app.controller('ActivationController', ['$q', '$scope', '$routeParams', '$location', 'Restangular',
                               function( $q,   $scope,   $routeParams,   $location,   Restangular) {
    var activations = Restangular.all('activations');
    var activation_success = undefined;
    var error_msg = "";

    $scope.get_error_msg = function() {
        return error_msg;
    }

    $scope.activate_user = function() {
        error_msg = "";
        var token = $routeParams.token;
        activations.post({token: token, password: $scope.user.password}).then(function(resp) {
            activation_success = true;
        }, function(response) {
            console.log(response);
            var deferred = $q.defer();
            if (response.status == 422) {
                activation_success = false;
                error_msg = response.data.password.join(', ');
                return deferred.reject(false);
            } else if (response.status == 410) {
                activation_success = false;
                error_msg = 'Invalid activation token, check your activation link';
                return deferred.reject(false);
            } else {
                throw new Error("No handler for status code " + response.status);
            }
        });
    };

    $scope.activation_success = function() {
        if (activation_success) {
            return true;
        }
        return false;
    }

    $scope.activation_error = function() {
        if (activation_success == false) {
            return true;
        }
        return false;
    }

}]);

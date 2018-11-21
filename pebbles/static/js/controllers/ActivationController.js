app.controller('ActivationController', ['$q', '$scope', '$routeParams', '$location', 'Restangular', 'AuthService',
                               function( $q,   $scope,   $routeParams,   $location,   Restangular,   AuthService) {
    var activation_success;
    var error_msg = "";

    $scope.get_error_msg = function() {
        return error_msg;
    };

    $scope.activate_user = function() {
        error_msg = "";
        var token = $routeParams.token;
        var promise = AuthService.changePasswordWithToken(token, $scope.user.password);
        promise.then(function(response) {
            activation_success = true;
            $scope.activated_user = response.eppn;
	    $.notify({message: 'You have successfully activated your account: ' + response.eppn + '. Please login with your email and password'}, {type: 'success'});
	    $location.path("/");
        }, function(response) {
            activation_success = false;
            if (response.status === 422) {
                error_msg = response.data.password.join(', ');
            } else if (response.status === 410) {
                error_msg = 'Invalid activation token, check your activation link';
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
    };

    $scope.activation_error = function() {
        if (activation_success === false) {
            return true;
        }
        return false;
    };

}]);

app.controller('ResetPasswordController', ['$q', '$scope', '$routeParams', 'AuthService', 'Restangular',
                                   function($q,   $scope,   $routeParams,   AuthService,   Restangular) {

    var token = $routeParams.token;
    var activations = Restangular.all('activations');
    var instructionsSent = false;
    var error_msg = "";

    $scope.requestReset = function() {
        activations.post({email: $scope.user.email}).then(function() {
            instructionsSent = true;
        });
    }

    $scope.reset_password = function() {
        var error_msg = "";
        var token = $routeParams.token;
        var promise = AuthService.changePasswordWithToken(token, $scope.user.password);
        promise.then(function() {
            activation_success = true;
        }, function(response) {
            activation_success = false;
            if (response.status == 422) {
                error_msg = response.data.password.join(', ');
            } else if (response.status == 410) {
                error_msg = 'Invalid activation token, check your activation link';
            } else {
                throw new Error("No handler for status code " + response.status);
            }
        });
    };

    $scope.showInstructionSentNotice = function() {
        return instructionsSent;
    }

    $scope.requestResetFormVisible = function() {
        if (token) {
            return false;
        }
        return true;
    };

    $scope.resetPasswordFormVisible = function() {
        if (token) {
            return true;
        }
        return false;
    };
}]);

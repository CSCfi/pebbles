app.controller('AuthController', ['$scope', '$location', 'AuthService', function($scope, $location, AuthService) {
    $scope.isLoggedIn = function() {
        return AuthService.isAuthenticated();
    };

    $scope.isLoggedOut = function() {
        return ! AuthService.isAuthenticated();
    };

    $scope.loginFormHidden = function(viewLocation) {
        return $location.path().match(viewLocation) === viewLocation;
    };

    $scope.login = function() {
        AuthService.login($scope.email, $scope.password).then(function() {
            $location.path("/dashboard");
        });
    };

    $scope.isAdmin = function() {
        return AuthService.isAdmin();
    };

    $scope.logout = function() {
        AuthService.logout();
        $scope.email = "";
        $scope.password = "";
        $location.path("/");
    };
}]);

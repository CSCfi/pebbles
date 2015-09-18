app.controller('NavbarController', ['$scope', '$location', 'AuthService', function($scope, $location, AuthService) {
    var _invalidLogin = false;

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
            _invalidLogin = false;
            $location.path("/dashboard");
        }, function() {
            _invalidLogin = true;
        });
    };

    $scope.isActive = function (viewLocation) { 
        return viewLocation === $location.path();
    };

    $scope.invalidLogin = function() {
        return _invalidLogin;
    };

    $scope.getUserName = function() {
        if ($scope.isLoggedIn()) {
            return AuthService.getUserName();
        }
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

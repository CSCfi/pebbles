app.controller('NavbarController', ['$scope', '$rootScope', '$location', 'AuthService', function($scope, $rootScope, $location, AuthService) {
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
            $rootScope.$broadcast('userLoggedIn');
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

    $scope.isGroupOwnerOrAdmin = function() {
        return AuthService.isGroupOwnerOrAdmin();
    };

    $scope.logout = function() {
        AuthService.logout();
        $scope.email = "";
        $scope.password = "";
        $rootScope.$broadcast('userLoggedOut');
        $location.path("/");
    };
}]);
